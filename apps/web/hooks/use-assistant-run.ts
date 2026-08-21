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
 *
 * None of that state is held here. It lives in the assistant store, because the two
 * surfaces rendering this conversation are mutually exclusive by viewport: crossing
 * 1024px unmounts one and mounts the other, and a `useState` in this hook would go
 * with it mid-turn. The hook is the behaviour; the store is the conversation.
 */

import { useCallback, useEffect } from "react"

import { getThreadMessages, recoverRun } from "@/lib/actions/assistant"
import type { ActionDecision } from "@/lib/api/types"
import { SseFrameReader, toRunEvent } from "@/lib/assistant/sse-frames"
import { buildTranscript } from "@/lib/assistant/transcript"
import {
  claimTurnKey,
  emptyRunSession,
  releaseTurnKey,
  type RunPhase,
} from "@/lib/stores/assistant-store"
import { useAssistantStore, useAssistantStoreApi } from "@/lib/stores/store-provider"

export type { RunPhase }

/** What one posted stream turned out to be. */
type PostedStream =
  | { ok: false; code: string }
  | { ok: true; terminal: boolean }

export function useAssistantRun(threadId: string | null) {
  const store = useAssistantStoreApi()
  const session = useAssistantStore((state) => state.session)
  // Narrowed to this thread, so a recovery running on another conversation neither
  // spins this one's button nor disables it.
  const recovering = useAssistantStore(
    (state) => state.recovering !== null && state.recovering === threadId,
  )

  // The session for the thread being asked about, which is empty whenever the held one
  // belongs to a different conversation.
  const active = session.threadId === threadId ? session : emptyRunSession(threadId)
  const transcript = buildTranscript(active.events)

  // The open stream is cancelled when the *provider* goes away, not when a surface
  // does. A surface unmounting is the breakpoint crossing this store exists to
  // survive, and aborting there would tear down the very stream being preserved —
  // so there is deliberately no unmount cleanup in this hook.
  //
  // A thread change is a different conversation, so the previous stream is cancelled
  // and this one's transcript is read from the server. `loadedThreadId` is what makes
  // that happen once per thread rather than once per mount: a remount mid-turn must
  // not abort the open stream and overwrite its events with the server's copy.
  useEffect(() => {
    const state = store.getState()
    const { transport } = state
    if (transport.loadedThreadId === threadId) return

    transport.abort?.abort()
    transport.abort = null
    releaseTurnKey(transport)
    transport.loadedThreadId = threadId

    if (!threadId) return

    let active = true

    void (async () => {
      const result = await getThreadMessages(threadId)
      if (!active) return
      if (!result.success) {
        // Released so reopening the thread reads it again, and stated so the learner
        // is not left looking at a blank transcript that claims nothing is wrong.
        // Holding the marker would make one blocked read permanent for the page.
        if (transport.loadedThreadId === threadId) transport.loadedThreadId = null
        state.updateSession(threadId, () => ({ problem: result.code }))
        return
      }
      state.updateSession(threadId, () => ({ events: result.data }))

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

      // `interrupted` is *not* abandoned — it is paused on a decision the learner
      // has yet to give, and the approval card is already rendered from its
      // `confirmation_required` event. A cancelled run has no terminal event,
      // though, so it needs the same resend/recovery offer as a dropped running run.
      if (run.data.status === "running" || run.data.status === "cancelled") {
        state.updateSession(threadId, () => ({ phase: "abandoned" }))
      }
    })()

    return () => {
      active = false
    }
  }, [threadId, store])

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
        store.getState().updateSession(forThreadId, (current) => ({
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
    [store],
  )

  /**
   * Posts one assistant request and reads its stream to completion.
   *
   * Shared by `send` and `decide`, which differ only in what they post and in
   * the turn-key rules around the call — those stay at the call sites because
   * they genuinely differ. Everything here is identical for both.
   *
   * `runId` stamps the streamed events: for a new turn it is the turn's own id,
   * which stands in because the wire format omits a run identity; for a decision
   * it is the paused run's real id.
   */
  const postStream = useCallback(
    async (
      forThreadId: string,
      url: string,
      body: unknown,
      runId: string,
      signal: AbortSignal,
    ): Promise<PostedStream> => {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal,
      })

      if (!response.ok) {
        return { ok: false, code: await readErrorCode(response) }
      }

      const terminal = await consume(response, forThreadId, runId)
      return { ok: true, terminal }
    },
    [consume],
  )

  /** Posts a turn and streams the reply. */
  const send = useCallback(
    async (content: string) => {
      if (!threadId) return
      const state = store.getState()
      const { transport } = state

      // A turn following an abandoned one is a *new* turn, so it gets a new key: the
      // server still holds a run under the old one, and reusing it would replay that
      // run and discard what was just typed. `claimTurnKey` states the rule.
      const turnId = claimTurnKey(transport, {
        fresh: state.session.threadId === threadId && state.session.phase === "abandoned",
      })

      const controller = new AbortController()
      transport.abort?.abort()
      transport.abort = controller
      state.updateSession(threadId, () => ({ phase: "streaming", problem: null }))

      try {
        const posted = await postStream(
          threadId,
          `/api/assistant/threads/${threadId}/messages`,
          { clientMessageId: turnId, content },
          turnId,
          controller.signal,
        )

        if (!posted.ok) {
          // A refusal is a *known* outcome, so the key is spent. On the capacity path
          // the server has already marked the run `FAILED`, so retrying with the same
          // key replays a run holding nothing but the original `user_message`: no
          // reply, no error, no explanation.
          releaseTurnKey(transport)
          state.updateSession(threadId, () => ({ phase: "idle", problem: posted.code }))
          return
        }

        if (posted.terminal) releaseTurnKey(transport)
        state.updateSession(threadId, () => ({ phase: posted.terminal ? "idle" : "abandoned" }))
      } catch {
        // An abort is this hook cancelling itself, not a failure to report.
        if (controller.signal.aborted) return
        state.updateSession(threadId, () => ({
          phase: "abandoned",
          problem: "stream_failed",
        }))
      }
    },
    [threadId, postStream, store],
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
      const state = store.getState()
      const { transport } = state

      const controller = new AbortController()
      transport.abort?.abort()
      transport.abort = controller
      state.updateSession(threadId, () => ({ phase: "streaming", problem: null }))

      try {
        const posted = await postStream(
          threadId,
          `/api/assistant/threads/${threadId}/actions/${actionId}/confirm`,
          { decision },
          runId,
          controller.signal,
        )

        if (!posted.ok) {
          // Where a stale approval surfaces: `validate_action_freshness` rejects an
          // approval the learner believes they just granted, and the code carries which
          // way it failed — expired, already resolved, or the resource moved on.
          // Unlike a refused turn, the key is not released here: the paused run is
          // still the live one, and its approval card remains on offer.
          state.updateSession(threadId, () => ({ phase: "idle", problem: posted.code }))
          return
        }

        if (posted.terminal) releaseTurnKey(transport)
        state.updateSession(threadId, () => ({ phase: posted.terminal ? "idle" : "abandoned" }))
      } catch {
        if (controller.signal.aborted) return
        state.updateSession(threadId, () => ({
          phase: "abandoned",
          problem: "stream_failed",
        }))
      }
    },
    [threadId, postStream, store],
  )

  /**
   * Re-reads what the server has persisted for this thread.
   *
   * Replay, not resume: the API answers with the rows it holds and closes. A run left
   * `RUNNING` server-side does not restart, so this can only ever show work that was
   * already recorded — never finish work that was abandoned.
   *
   * It takes no run id, and deliberately so. A streamed frame is `id: <sequence>` with
   * no run identity, so a live turn's events are stamped with the turn's key as a
   * stand-in. That stand-in is not a run UUID: passing it to the run query endpoint
   * would 404 as `assistant_run_not_found`, which is exactly the failure a recovery
   * path must not have. The thread read needs no id, returns every run's events, and
   * carries the server's real `runId` on each one — so it both recovers the transcript
   * and replaces the synthetic ids with true ones.
   */
  const recover = useCallback(async () => {
    if (!threadId) return
    const state = store.getState()

    state.setRecovering(threadId)
    try {
      const refreshed = await getThreadMessages(threadId)
      if (!refreshed.success) {
        state.updateSession(threadId, () => ({ problem: refreshed.code }))
        return
      }

      // Replaced rather than appended: the same events are already held under
      // synthetic ids, and merging the two identities would render the turn twice.
      state.updateSession(threadId, () => ({ events: refreshed.data }))

      // The thread read carries events, not run status, so whether the run is still
      // unfinished is asked of the run itself — now that a real id is known.
      const runId = buildTranscript(refreshed.data).activeRunId
      if (!runId) {
        state.updateSession(threadId, () => ({ phase: "idle" }))
        return
      }

      const run = await recoverRun(threadId, runId)
      // A failed status read is not a failed recovery: the transcript was still
      // restored. Leaving the phase alone keeps the resend offer, which is the safe
      // reading — it never claims a run finished when that is unconfirmed.
      if (!run.success) return

      const unfinished =
        run.data.status === "running" ||
        run.data.status === "interrupted" ||
        run.data.status === "cancelled"
      if (!unfinished) releaseTurnKey(state.transport)
      state.updateSession(threadId, () => ({ phase: unfinished ? "abandoned" : "idle" }))
    } finally {
      // Cleared only if this thread's own recovery is still the outstanding one. A
      // recovery started on another conversation while this was in flight owns the
      // marker now, and clearing it here would re-enable that thread's controls
      // mid-read.
      const current = store.getState()
      if (current.recovering === threadId) current.setRecovering(null)
    }
  }, [threadId, store])

  /** Discards the turn key so the next send starts a fresh run. */
  const resetTurn = useCallback(() => {
    const state = store.getState()
    releaseTurnKey(state.transport)
    state.updateSession(threadId, () => ({ phase: "idle", problem: null }))
  }, [threadId, store])

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
