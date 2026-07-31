import { execFile } from "node:child_process"
import { promisify } from "node:util"

import { repoRoot } from "./env"

const run = promisify(execFile)

/**
 * Stopping and starting Centrifugo, so a spec can prove re-subscribe recovery.
 *
 * This is the third deliberate exception to the API-only rule, and the reason is that
 * the failure being tested is an infrastructure failure. A rubric grade is delivered
 * to the browser over a Centrifugo subscription; if that socket dies while the worker
 * is still grading, the verdict is published to a client that is not listening. What
 * must then happen is that the client re-subscribes and the snapshot it receives
 * carries the grade that was missed (`lib/study/grade-snapshot.ts`).
 *
 * Nothing short of actually killing the process tests that. Blocking the route in the
 * browser would exercise the client's reconnect logic against a server that never
 * went away, which is a different and much weaker claim: the interesting half is that
 * the *recovery* replays state the client did not see live.
 */

/** The compose service name, matching `docker-compose.yml`. */
export const composeRealtimeService = "centrifugo"

/**
 * Restarts Centrifugo and waits for compose to report it healthy again.
 *
 * `restart` rather than `stop` then `start`: it is one command, so a spec that fails
 * between the two cannot leave the stack down for every spec that follows. The
 * healthcheck wait matters just as much — returning as soon as the container is
 * *running* would hand back a Centrifugo that is not yet accepting subscriptions, and
 * the reconnect under test would fail for a reason the spec did not intend.
 */
export async function restartRealtime({
  timeoutMs = 120_000,
}: { timeoutMs?: number } = {}): Promise<void> {
  await compose(["restart", composeRealtimeService])

  const deadline = Date.now() + timeoutMs
  let last = ""
  while (Date.now() < deadline) {
    last = await compose([
      "ps",
      "--format",
      "{{.Service}} {{.State}} {{.Health}}",
      composeRealtimeService,
    ])
    if (/\brunning\b/.test(last) && /\bhealthy\b/.test(last)) return
    await new Promise((resolve) => setTimeout(resolve, 1_000))
  }

  throw new Error(
    `Centrifugo did not become healthy within ${timeoutMs}ms after a restart.\n\n` +
      `Last status: ${last || "(no output)"}\n\n` +
      "Every realtime spec depends on this service, so the run is stopped here " +
      "rather than left to fail one assertion at a time.",
  )
}

async function compose(args: string[]): Promise<string> {
  try {
    const { stdout } = await run("docker", ["compose", ...args], {
      cwd: repoRoot,
      maxBuffer: 1024 * 1024,
    })
    return stdout.trim()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      `docker compose ${args.join(" ")} failed.\n\n` +
        "The realtime specs drive the real container because a dropped " +
        "subscription is the thing being tested.\n\n" +
        detail,
    )
  }
}
