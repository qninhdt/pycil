/**
 * Projects a settled grading task snapshot into the verdict the screen renders.
 *
 * A free-text answer is graded by a worker, not in the request, so its verdict
 * arrives over the realtime channel as a task snapshot rather than in the
 * `/answers` response. This is the seam between those two shapes.
 *
 * Deriving the verdict here — at render, from the snapshot — rather than copying it
 * into the session reducer is deliberate. The task id is persisted, so a reload
 * re-subscribes and the replayed snapshot rebuilds the same verdict; a reducer copy
 * would be a second source of truth that a reload silently loses.
 *
 * The result object is camelCase at the top level (the worker builds it that way)
 * while `reveal` keeps the dictionary's snake_case keys, because it is passed
 * through from upstream untouched. Nothing here may be case-transformed wholesale.
 */

import type { AsyncTaskSnapshot } from "@/lib/realtime/task-snapshot"
import type { Reveal } from "@/lib/api/types"

import type { Verdict } from "./session-machine"

export type PendingGradeStatus =
  | { kind: "waiting" }
  /** The grade landed. This is the only variant that carries a verdict. */
  | { kind: "settled"; verdict: Verdict }
  /** The grade will not arrive. Carries a code when the server supplied one. */
  | { kind: "failed"; code: string | null }

/**
 * Reads a snapshot for an outstanding grade.
 *
 * A null snapshot means nothing has arrived yet, which is not a failure: the
 * subscribe proxy replays the latest persisted state, so waiting is the normal
 * first observation.
 */
export function readPendingGrade(
  snapshot: AsyncTaskSnapshot | null,
): PendingGradeStatus {
  if (!snapshot) return { kind: "waiting" }

  switch (snapshot.status) {
    case "succeeded":
      return { kind: "settled", verdict: verdictFromResult(snapshot.result) }

    // `expired` is as terminal as `failed` for the learner: the answer was taken
    // and no mark is coming, so it is stated rather than spun on forever.
    case "failed":
    case "expired":
      return { kind: "failed", code: snapshot.errorCode }

    case "queued":
    case "running":
      return { kind: "waiting" }
  }
}

/**
 * Builds a verdict from the worker's result payload.
 *
 * Every field is read defensively because the payload is typed as an open record on
 * the wire. A missing field becomes null rather than a thrown read, so a partial
 * result still renders the part that arrived instead of blanking the screen at the
 * moment the learner is waiting for it.
 */
function verdictFromResult(result: Record<string, unknown> | null): Verdict {
  return {
    isCorrect: asBoolean(result?.isCorrect),
    score: asNumber(result?.gradeScore),
    feedback: asString(result?.gradeFeedback),
    reveal: asReveal(result?.reveal),
    masteryBefore: asNumber(result?.masteryBefore),
    masteryAfter: asNumber(result?.masteryAfter),
  }
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null
}

function asReveal(value: unknown): Reveal | null {
  return value && typeof value === "object" ? (value as Reveal) : null
}
