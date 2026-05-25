"use client";

/**
 * Subscribe to a job's SSE stream and surface its lifecycle to a React tree.
 *
 * The server emits 3 event types: `status`, `result`, `error`. Once `result`
 * or `error` lands, the EventSource is closed and `state` becomes terminal.
 */
import { useEffect, useState } from "react";

export type JobState =
  | { kind: "pending" }
  | { kind: "completed"; result: unknown }
  | { kind: "failed"; error: string };

export function useJobStream(jobId: string | null | undefined): JobState {
  const [state, setState] = useState<JobState>({ kind: "pending" });

  useEffect(() => {
    if (!jobId) return;
    setState({ kind: "pending" });

    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    es.addEventListener("status", () => {
      // status pings keep the connection alive; nothing to apply.
    });
    es.addEventListener("result", (ev: MessageEvent) => {
      try {
        const result = JSON.parse(ev.data);
        setState({ kind: "completed", result });
      } catch {
        setState({ kind: "completed", result: ev.data });
      }
      es.close();
    });
    es.addEventListener("error", (ev: MessageEvent) => {
      let detail = "stream_error";
      try {
        if (ev.data) {
          const parsed = JSON.parse(ev.data);
          detail = parsed?.error ?? detail;
        }
      } catch {
        /* keep default */
      }
      setState({ kind: "failed", error: detail });
      es.close();
    });

    return () => es.close();
  }, [jobId]);

  return state;
}
