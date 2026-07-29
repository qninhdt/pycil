"use client"

/**
 * Driving one thread's assistant conversation.
 *
 * This owns the transport: it posts a turn, reads the SSE body, folds frames into a
 * transcript, and knows how to replay after a dropped connection. The fold itself
 * lives in `lib/assistant/transcript.ts` so the streamed and replayed paths cannot
 * diverge.
 *
 * A transcript is a *sequence of streams*, not one long one. `confirmation_required`
 * ends its stream, and posting the decision returns a fresh stream that continues the
 * same run. So this hook accumulates events across streams and never assumes the
 * connection it opened will carry the run to completion.
 */

import { useCallback, useEffect, useRef, useState } from "react"

import { getThreadMessages, recoverRun } from "@/lib/actions/assistant"
import type { ActionDecision, RunEvent } from "@/lib/api/types"
import { SseFrameReader, toRunEvent } from "@/lib/assistant/sse-frames"
import { buildTranscript } from "@/lib/assistant/transcript"

/** Why the composer is unavailable, when it is. */
export type RunPhase =
  | "idle"
  /** A stream is open and events are arriving. */
  | "streaming"
  /** The stream closed with no terminal event: the run was abandoned server-side. */
  | "abandoned"

/**
 * One thread's conversation state, tagged with the thread it belongs to.
 *
 * The tag is what makes this safe. Every write goes through `update`, which drops the
 * write if the thread has moved on — so a `getThreadMessages` that resolves after the
 * learner switched conversations cannot pour thread A's transcript into thread B. It
 * also means a thread change needs no reset effect: a mismatched tag already reads as
 * empty, which is both correct and one fewer render.
 */
interface Session {
  threadId: string | null
  events: RunEvent[]
  phase: RunPhase
  /** A wire error code from a failed submission, not from a failed run. */
  problem: string | null
}

function emptySession(threadId: string | null): Session {
  return { threadId, events: [], phase: "idle", problem: null }
}

export function useAssistantRun(threadId: string | null) {
  const [session, setSession] = useState<Session>(() => emptySession(null))
  // True while a recovery read is outstanding, so the button that started it can say
  // so. Separate from `phase`, because recovering does not change what the run is: a
  // run that was abandoned is still abandoned while its transcript is being re-read.
  const [recovering, setRecovering] = useState(false)

  // The reader is aborted on unmount and on thread change. Without this, closing the
  // drawer mid-stream leaves a reader holding an open response body.
  const abort = useRef<AbortController | null>(null)
  // The turn's idempotency key, minted once and reused across transport retries: the
  // API returns the existing run's events for a repeated id rather than starting a
  // second run.
  const clientMessageId = useRef<string | null>(null)

  // The session for the thread being asked about, which is empty whenever the held one
  // belongs to a different conversation.
  const active = session.threadId === threadId ? session : emptySession(threadId)
  const transcript = buildTranscript(active.events)

  /** Applies a patch, unless the thread it was computed for is no longer open. */
  const update = useCallback(
    (forThreadId: string | null, patch: (current: Session) => Partial<Session>) => {
      setSession((current) => {
        const base =
          current.threadId === forThreadId ? current : emptySession(forThreadId)
        return { ...base, ...patch(base) }
      })
    },
    [],
  )

  useEffect(() => {
    return () => {
      abort.current?.abort()
      abort.current = null
    }
  }, [])

  // A thread change is a different conversation, so the previous stream is cancelled
  // and this one's transcript is read from the server. Only the abort and the fetch
  // happen here: the state itself is derived above rather than reset, which is why
  // there is no synchronous write in this effect.
  useEffect(() => {
    abort.current?.abort()
    abort.current = null
    clientMessageId.current = null

    if (!threadId) return

    let active = true

    void (async () => {
      const result = await getThreadMessages(threadId)
      if (!active || !result.success) return
      update(threadId, () => ({ events: result.data }))

      // Whether the newest run is still unfinished. Without this a reload was a dead
      // end: the fold leaves the last assistant turn `streaming` because no terminal
      // event ever arrived, so the caret blinks for a run nothing is reading, the
      // recovery notice never appears because `phase` is still `idle`, and any new
      // message is refused with `assistant_thread_run_active`. The thread looked busy
      // forever with no offered way out.
      const runId = buildTranscript(result.data).activeRunId
      if (!runId) return

      const run = await recoverRun(threadId, runId)
      if (!active || !run.success) return

      // `running` only, deliberately. An `interrupted` run is *not* abandoned — it is
      // paused on a decision the learner has yet to give, and the approval card is
      // already rendered from its `confirmation_required` event. Telling them the
      // connection dropped would be false, and would offer a resend in place of the
      // approve/reject they actually owe.
      if (run.data.status === "running") {
        update(threadId, () => ({ phase: "abandoned" }))
      }
    })()

    return () => {
      active = false
    }
  }, [threadId, update])

  /**
   * Reads one stream to completion, appending events as they arrive.
   *
   * Returns whether a terminal event was seen. A false means the body ended without
   * `done`, `error`, or an approval pause — which server-side means the run is still
   * marked running with its work abandoned, and the only honest recovery is to resend
   * the turn.
   */
  const consume = useCallback(
    async (
      response: Response,
      forThreadId: string,
      runId: string,
    ): Promise<boolean> => {
      const body = response.body
      if (!body) return false

      const reader = body.getReader()
      const frames = new SseFrameReader()
      let terminal = false

      const apply = (parsed: ReturnType<SseFrameReader["push"]>) => {
        if (parsed.length === 0) return
        const incoming = parsed.map((frame) => toRunEvent(frame, runId))
        if (
          incoming.some(
            (event) =>
              event.eventType === "done" ||
              event.eventType === "error" ||
              event.eventType === "confirmation_required",
          )
        ) {
          terminal = true
        }
        update(forThreadId, (current) => ({
          events: [...current.events, ...incoming],
        }))
      }

      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          if (value) apply(frames.push(value))
        }
        apply(frames.flush())
      } finally {
        reader.releaseLock()
      }

      return terminal
    },
    [update],
  )

  /** Posts a turn and streams the reply. */
  const send = useCallback(
    async (content: string) => {
      if (!threadId) return

      // Minted once per turn: a retry of the same turn reuses it so the server joins
      // the existing run instead of starting a duplicate.
      //
      // "The same turn" is the load-bearing part. The key is only reused while the
      // turn it belongs to is still unresolved, which is why `abandoned` clears it
      // here: after a dropped stream the server holds a run under that key, and
      // sending *new* content with it takes the API's `not created` branch, which
      // replays the old run's events and discards what was just typed. The learner's
      // message would vanish with no error and the previous reply would appear in its
      // place. A new turn therefore always gets a new key.
      if (active.phase === "abandoned") clientMessageId.current = null
      clientMessageId.current ??= crypto.randomUUID()
      const turnId = clientMessageId.current

      const controller = new AbortController()
      abort.current?.abort()
      abort.current = controller
      update(threadId, () => ({ phase: "streaming", problem: null }))

      try {
        const response = await fetch(`/api/assistant/threads/${threadId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ clientMessageId: turnId, content }),
          signal: controller.signal,
        })

        if (!response.ok) {
          // The key is spent. Reuse is only safe while the outcome is *unknown* — a
          // dropped request that may or may not have been accepted. A refusal is a
          // known outcome, and on the capacity path the server has already marked the
          // run `FAILED` (`router.py:258-261`), so retrying with the same key takes the
          // `not created` branch and replays a run holding nothing but the original
          // `user_message`: no reply, no error, no explanation.
          clientMessageId.current = null
          const code = await readErrorCode(response)
          update(threadId, () => ({ phase: "idle", problem: code }))
          return
        }

        // The turn's own id stands in for the run id, which the wire format omits.
        const terminal = await consume(response, threadId, turnId)
        // A completed turn releases the key. Keeping it would make the learner's next
        // message join the finished run and return its replay instead of answering.
        if (terminal) clientMessageId.current = null
        update(threadId, () => ({ phase: terminal ? "idle" : "abandoned" }))
      } catch {
        // An abort is this hook cancelling itself, not a failure to report.
        if (controller.signal.aborted) return
        update(threadId, () => ({ phase: "abandoned", problem: "stream_failed" }))
      }
    },
    [threadId, active.phase, consume, update],
  )

  /**
   * Submits an approval decision, whose response continues the same run.
   *
   * `runId` is the approval turn's own, not a fresh one: the returned stream carries
   * more events of the run that paused, and stamping them with a new identity would
   * split one conversation into two and restart the replay cursor mid-run.
   */
  const decide = useCallback(
    async (runId: string, actionId: string, decision: ActionDecision) => {
      if (!threadId) return

      const controller = new AbortController()
      abort.current?.abort()
      abort.current = controller
      update(threadId, () => ({ phase: "streaming", problem: null }))

      try {
        const response = await fetch(
          `/api/assistant/threads/${threadId}/actions/${actionId}/confirm`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision }),
            signal: controller.signal,
          },
        )

        if (!response.ok) {
          // Where a stale approval surfaces: `validate_action_freshness` rejects an
          // approval the learner believes they just granted, and the code carries which
          // way it failed — expired, already resolved, or the resource moved on.
          const code = await readErrorCode(response)
          update(threadId, () => ({ phase: "idle", problem: code }))
          return
        }

        const terminal = await consume(response, threadId, runId)
        if (terminal) clientMessageId.current = null
        update(threadId, () => ({ phase: terminal ? "idle" : "abandoned" }))
      } catch {
        if (controller.signal.aborted) return
        update(threadId, () => ({ phase: "abandoned", problem: "stream_failed" }))
      }
    },
    [threadId, consume, update],
  )

  /**
   * Re-reads what the server has persisted for this thread.
   *
   * Replay, not resume: the API answers with the rows it holds and closes. A run left
   * `RUNNING` server-side does not restart, so this can only ever show work that was
   * already recorded — never finish work that was abandoned.
   *
   * It takes no run id, and deliberately so. A streamed frame is `id: <sequence>` with
   * no run identity, so a live turn's events are stamped with the turn's
   * `clientMessageId` as a stand-in. That stand-in is not a run UUID: passing it to the
   * run query endpoint would 404 as `assistant_run_not_found`, which is exactly the
   * failure a recovery path must not have. The thread read needs no id, returns every
   * run's events, and carries the server's real `runId` on each one — so it both
   * recovers the transcript and replaces the synthetic ids with true ones.
   */
  const recover = useCallback(async () => {
    if (!threadId) return

    setRecovering(true)
    try {
      const refreshed = await getThreadMessages(threadId)
      if (!refreshed.success) {
        update(threadId, () => ({ problem: refreshed.code }))
        return
      }

      // Replaced rather than appended: the same events are already held under
      // synthetic ids, and merging the two identities would render the turn twice.
      update(threadId, () => ({ events: refreshed.data }))

      // The thread read carries events, not run status, so whether the run is still
      // unfinished is asked of the run itself — now that a real id is known.
      const runId = buildTranscript(refreshed.data).activeRunId
      if (!runId) {
        update(threadId, () => ({ phase: "idle" }))
        return
      }

      const run = await recoverRun(threadId, runId)
      // A failed status read is not a failed recovery: the transcript was still
      // restored. Leaving the phase alone keeps the resend offer, which is the safe
      // reading — it never claims a run finished when that is unconfirmed.
      if (!run.success) return

      const unfinished =
        run.data.status === "running" || run.data.status === "interrupted"
      update(threadId, () => ({ phase: unfinished ? "abandoned" : "idle" }))
    } finally {
      setRecovering(false)
    }
  }, [threadId, update])

  /** Discards the turn key so the next send starts a fresh run. */
  const resetTurn = useCallback(() => {
    clientMessageId.current = null
    update(threadId, () => ({ phase: "idle", problem: null }))
  }, [threadId, update])

  return {
    transcript,
    phase: active.phase,
    problem: active.problem,
    recovering,
    send,
    decide,
    recover,
    resetTurn,
  }
}

/**
 * The wire error code from a failed response.
 *
 * The envelope is `{error: {code}}`. A body that is not that shape still has to
 * produce something the taxonomy can classify, so an unreadable one becomes
 * `unexpected` rather than throwing inside an error path.
 */
async function readErrorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    const code = (body as { error?: { code?: unknown } })?.error?.code
    return typeof code === "string" ? code : "unexpected"
  } catch {
    return "unexpected"
  }
}
