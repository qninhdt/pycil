/**
 * Folding a run's flat event list into renderable turns.
 *
 * The API stores events, not messages: a single assistant reply arrives as dozens of
 * `token` events that have to be concatenated, with `tool_call` and `tool_result`
 * interleaved between them. This module is the one place that fold happens, so the
 * streamed path and the replayed path cannot disagree about what a transcript looks
 * like.
 *
 * That shared fold is the point. A transcript is rebuilt from `GET .../messages` on
 * open and then extended by the live stream, and a second implementation for one of
 * those two would eventually render the same run differently depending on whether
 * the learner reloaded.
 */

import { assertNever } from "./exhaustive"
import type { RunEvent } from "@/lib/api/types"

/** What the learner sent. */
export interface UserTurn {
  kind: "user"
  key: string
  content: string
}

/**
 * What the assistant said, accumulated from its tokens.
 *
 * `streaming` is true while no terminal event has been seen for this turn, which is
 * what drives the caret and stops the composer from accepting a second submission.
 */
export interface AssistantTurn {
  kind: "assistant"
  key: string
  content: string
  streaming: boolean
}

/** A tool the model invoked, with its result once one arrives. */
export interface ToolTurn {
  kind: "tool"
  key: string
  tool: string
  /** Null while the call is outstanding. Truncated to 1000 chars server-side. */
  result: string | null
}

/** The run paused for a human decision. Terminal for its stream. */
export interface ApprovalTurn {
  kind: "approval"
  key: string
  /**
   * The run this approval belongs to, so its continuation groups with it.
   *
   * Posting the decision opens a *new* stream carrying more of this same run, and
   * those events have to be stamped with the identity the approval already used.
   * Taking it from the turn rather than re-deriving it means the continuation lands
   * in the right run whether the approval arrived live or from a replay.
   */
  runId: string
  actionId: string
  tool: string
  expiresAt: string
  /**
   * The owned nodes the tool would act on, keyed by argument name.
   *
   * Names, not ids. The card has to say what is about to be deleted, and a UUID
   * tells the learner nothing they can consent to. Empty when the tool targets
   * nothing nameable, which the card renders as an explicit caveat rather than
   * silently omitting.
   */
  targets: Record<string, string>
}

/** The run failed. Carries the server's own code, never a guess. */
export interface ErrorTurn {
  kind: "error"
  key: string
  code: string
}

export type Turn = UserTurn | AssistantTurn | ToolTurn | ApprovalTurn | ErrorTurn

export interface Transcript {
  turns: Turn[]
  /**
   * The newest run in the transcript, or null when the thread is empty.
   *
   * This is how recovery becomes reachable at all: the run query endpoint needs a
   * run id, and a client that has only ever read `GET .../messages` would otherwise
   * never learn one. It is derived here rather than tracked separately so it cannot
   * disagree with the events actually held.
   */
  activeRunId: string | null
  /**
   * Set while the run waits on a decision, so the composer stays closed.
   *
   * Cleared by the next event in the same run, because posting a decision returns a
   * stream that continues it — so anything arriving after the pause is proof the
   * decision was given. Without that clearing the composer stayed shut for the rest
   * of the thread's life after a single approval.
   */
  awaitingApproval: ApprovalTurn | null
}

// A `cursor` field lived here to carry `Last-Event-ID` for a stream resume. It is
// gone because the resume it was for does not exist: the API replays persisted rows
// and closes, so recovery re-reads the thread instead, and a cursor no caller read
// was only a claim the transport could not honour. `settled` went the same way — the
// UI branches on `phase`, which distinguishes a closed socket from a finished run,
// which is the distinction that actually matters.

/**
 * Folds events into a transcript.
 *
 * Pure and total: it takes the whole event list every time rather than mutating an
 * accumulator, so replaying a run and streaming it produce the same value, and the
 * function can be tested without a stream. Event lists here are one run's worth of
 * turns, so re-folding is cheap.
 *
 * Out-of-order and duplicate events are handled by sorting and de-duplicating on
 * `(runId, sequence)` first. Both occur in practice: a replay after a dropped stream
 * re-sends events the client already had, and the sequence is the only thing that
 * orders them within a run.
 *
 * The run id is half of that identity because `sequence` restarts at 1 for every
 * run: it is `run.event_cursor`, incremented per run rather than per thread. A
 * thread's persisted transcript spans several runs, so keying on `sequence` alone
 * made run 2's first event collide with run 1's and silently dropped most of a
 * multi-turn conversation.
 */
export function buildTranscript(events: RunEvent[]): Transcript {
  const ordered = dedupeByRunAndSequence(events)

  const turns: Turn[] = []
  let awaitingApproval: ApprovalTurn | null = null
  // The run the newest event belongs to. Events arrive grouped by run in
  // chronological order, so the last one seen is the current run — which is the id
  // recovery needs.
  let latestRunId: string | null = null

  for (const event of ordered) {
    latestRunId = event.runId

    // Cleared on every event, and re-armed below only by `confirmation_required`.
    // So the flag survives the fold only when the approval is the *last* event held,
    // which is exactly when the run is still waiting on a decision.
    //
    // This has to be unconditional rather than handled in the terminal arms. A
    // decision resumes the run on a new stream and the API emits nothing to say
    // "decided" — the resumption itself is the signal, and it usually begins with
    // tokens or another tool call rather than `done`. Clearing only on `done` left
    // the flag set for the rest of the thread's life, which disabled the composer
    // permanently and kept the answered request on screen as though still actionable.
    awaitingApproval = null

    switch (event.eventType) {
      case "user_message": {
        turns.push({
          kind: "user",
          key: turnKey("u", event),
          content: event.payload.content,
        })
        break
      }

      case "token": {
        // Appended to the open assistant turn rather than pushed as its own, which
        // is the whole reason this fold exists: one reply is hundreds of these.
        const open = lastAssistantTurn(turns)
        if (open) {
          open.content += event.payload.content
        } else {
          turns.push({
            kind: "assistant",
            key: turnKey("a", event),
            content: event.payload.content,
            streaming: true,
          })
        }
        break
      }

      case "tool_call": {
        // A tool call closes the current assistant turn: text after it is a new
        // paragraph of reasoning, not a continuation of the sentence before.
        closeAssistantTurn(turns)
        turns.push({
          kind: "tool",
          key: turnKey("t", event),
          tool: event.payload.tool,
          result: null,
        })
        break
      }

      case "tool_result": {
        // Matched to its call by tool name, latest first. The API emits no call id,
        // so this is the only available join; two concurrent calls to the same tool
        // would be indistinguishable, which the transcript accepts rather than
        // inventing an id the server never sent.
        const call = lastPendingToolTurn(turns, event.payload.tool)
        if (call) {
          call.result = event.payload.content
        } else {
          turns.push({
            kind: "tool",
            key: turnKey("t", event),
            tool: event.payload.tool,
            result: event.payload.content,
          })
        }
        break
      }

      case "confirmation_required": {
        closeAssistantTurn(turns)
        const approval: ApprovalTurn = {
          kind: "approval",
          key: turnKey("c", event),
          runId: event.runId,
          actionId: event.payload.action_id,
          tool: event.payload.tool,
          expiresAt: event.payload.expires_at,
          // Defaulted because the field is newer than the oldest persisted events:
          // a replayed approval from before the API carried target names has none,
          // and the card falls back to naming just the tool.
          targets: event.payload.targets ?? {},
        }
        turns.push(approval)
        awaitingApproval = approval
        // This event ends its stream. The run continues only when a decision is
        // posted, and that returns a *new* stream, so the transcript is a sequence
        // of streams rather than one long one.
        break
      }

      case "done": {
        closeAssistantTurn(turns)
        break
      }

      case "error": {
        closeAssistantTurn(turns)
        turns.push({
          kind: "error",
          key: turnKey("e", event),
          code: event.payload.code,
        })
        break
      }

      // Adding an event type to `RunEventType` without an arm above fails the
      // typecheck here. Without this the new event would be silently dropped: the
      // switch sits in a loop and every arm `break`s, so an unmatched event is
      // indistinguishable from one deliberately ignored.
      default:
        assertNever(event, "run event type")
    }
  }

  return { turns, activeRunId: latestRunId, awaitingApproval }
}

/**
 * A stable React key for one turn.
 *
 * Both halves of the event identity are in it. `sequence` alone repeats across runs,
 * so a thread of several turns produced duplicate keys — which React resolves by
 * reusing the wrong element, showing a previous turn's text under a new one.
 */
function turnKey(prefix: string, event: RunEvent): string {
  return `${prefix}-${event.runId}-${event.sequence}`
}

/**
 * Ordered by run then sequence, with duplicates dropped.
 *
 * Keyed on `(runId, sequence)` rather than sequence alone, because the API's sequence
 * is `run.event_cursor` — **per run**, not per thread. `GET .../messages` returns
 * every run in the thread, so each turn restarts at 1. Keying on sequence alone made
 * turn two's first event collide with turn one's, which silently discarded most of a
 * multi-turn transcript.
 *
 * De-duplication is still needed for the overlap case: a replay re-sends events the
 * client already holds, and applying a token twice would double the visible text.
 *
 * Runs are ordered by first appearance rather than by id, since a run id is a UUID
 * and sorting on it would shuffle the conversation. The server returns runs in
 * chronological order, so arrival order is the chronology.
 */
function dedupeByRunAndSequence(events: RunEvent[]): RunEvent[] {
  const seen = new Map<string, RunEvent>()
  const runOrder = new Map<string, number>()

  for (const event of events) {
    if (!runOrder.has(event.runId)) runOrder.set(event.runId, runOrder.size)
    const key = `${event.runId}:${event.sequence}`
    if (!seen.has(key)) seen.set(key, event)
  }

  return [...seen.values()].sort((a, b) => {
    const runDelta = runOrder.get(a.runId)! - runOrder.get(b.runId)!
    return runDelta !== 0 ? runDelta : a.sequence - b.sequence
  })
}

/** The trailing assistant turn, if the last turn is one still being written. */
function lastAssistantTurn(turns: Turn[]): AssistantTurn | null {
  const last = turns[turns.length - 1]
  return last?.kind === "assistant" && last.streaming ? last : null
}

function closeAssistantTurn(turns: Turn[]): void {
  const open = lastAssistantTurn(turns)
  if (open) open.streaming = false
}

/** The most recent call to this tool that has no result yet. */
function lastPendingToolTurn(turns: Turn[], tool: string): ToolTurn | null {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    const turn = turns[index]
    if (turn.kind === "tool" && turn.tool === tool && turn.result === null) return turn
  }
  return null
}
