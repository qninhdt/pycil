/**
 * SSE handler for job progress.
 *
 * Strategy: Postgres-first to avoid race window between worker publish + client
 * subscribe. If the job is already terminal, emit one event and close. Else
 * subscribe to `results:{term_id}` (term-keyed for cross-user dedup; multiple
 * users adding the same term share a single worker run). Heartbeat every 15s.
 */
import type { NextRequest } from "next/server";
import { createClient } from "redis";

import { auth } from "@/auth";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HEARTBEAT_MS = 15_000;
const TIMEOUT_MS = 5 * 60_000;

interface JobRow {
  id: string;
  status: string;
  payload: { term_id?: number } | null;
  result: unknown;
  error: string | null;
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
): Promise<Response> {
  const session = await auth();
  if (!session?.user?.id) {
    return new Response("unauthorized", { status: 401 });
  }
  const { id: jobId } = await params;

  const own = await pool.query(
    "SELECT 1 FROM user_term_jobs WHERE user_id = $1 AND job_id = $2 LIMIT 1",
    [session.user.id, jobId]
  );
  if (own.rowCount === 0) {
    return new Response("forbidden", { status: 403 });
  }

  const initial = await pool.query<JobRow>(
    "SELECT id::text, status, payload, result, error FROM jobs WHERE id = $1",
    [jobId]
  );
  if (initial.rowCount === 0) {
    return new Response("not_found", { status: 404 });
  }
  const row = initial.rows[0];
  const termId = row.payload?.term_id;

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };

      send("status", { status: row.status });

      if (row.status === "completed") {
        send("result", row.result);
        controller.close();
        return;
      }
      if (row.status === "failed") {
        send("error", { error: row.error ?? "unknown" });
        controller.close();
        return;
      }
      if (termId === undefined) {
        send("error", { error: "missing_term_id" });
        controller.close();
        return;
      }

      const sub = createClient({ url: process.env.REDIS_URL });
      let closed = false;
      const heartbeat = setInterval(() => {
        if (!closed) controller.enqueue(encoder.encode(`: hb\n\n`));
      }, HEARTBEAT_MS);
      const timeout = setTimeout(() => {
        if (!closed) {
          send("error", { error: "timeout" });
          cleanup();
        }
      }, TIMEOUT_MS);

      const cleanup = async () => {
        if (closed) return;
        closed = true;
        clearInterval(heartbeat);
        clearTimeout(timeout);
        try {
          await sub.unsubscribe();
          await sub.quit();
        } catch {
          /* ignore */
        }
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      request.signal.addEventListener("abort", () => void cleanup());

      try {
        await sub.connect();
        await sub.subscribe(`results:${termId}`, (message) => {
          try {
            const parsed = JSON.parse(message);
            if (parsed?.error) {
              send("error", parsed);
            } else {
              send("result", parsed);
            }
          } catch {
            send("result", { raw: message });
          }
          void cleanup();
        });

        // Race-safe re-check: job may have completed between the initial SELECT
        // and the SUBSCRIBE landing. Without this, the client hangs forever.
        const recheck = await pool.query<JobRow>(
          "SELECT status, result, error FROM jobs WHERE id = $1",
          [jobId]
        );
        const r = recheck.rows[0];
        if (r && r.status === "completed") {
          send("result", r.result);
          await cleanup();
        } else if (r && r.status === "failed") {
          send("error", { error: r.error ?? "unknown" });
          await cleanup();
        }
      } catch (err) {
        send("error", { error: String(err) });
        await cleanup();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      connection: "keep-alive",
    },
  });
}
