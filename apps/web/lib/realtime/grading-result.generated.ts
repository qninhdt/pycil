/**
 * Generated from packages/shared-py/shared/realtime/payloads.py by scripts/extract-realtime-contracts.py. Do not edit.
 *
 * Source fingerprint: cb68c663c993
 *
 * The inner `result` payload of a settled grading task.
 *
 * `task-snapshot.ts` validates the envelope around this properly and then
 * stops at `Record<string, unknown>`, so every field below used to be read
 * by bare string key. Those reads are defensive — a mismatch becomes null,
 * not a throw — which means renaming a field on the Python side produced a
 * blank verdict for a learner who had just answered, with nothing red
 * anywhere to say so.
 *
 * Field names are the wire names from `GradingResult.to_dict()`, not the
 * dataclass attributes: the class is snake_case and that method is where
 * the camelCase mapping is stated.
 *
 * Regenerate with:  python3 scripts/extract-realtime-contracts.py
 */

export interface GradingResultPayload {
  responseId: string
  senseId: number
  isCorrect: boolean
  gradeScore: number
  gradeFeedback: string | null
  masteryBefore: number | null
  masteryAfter: number | null
  renderFormat: string
  reveal: Record<string, unknown> | null
}

/** Every key the payload carries, in wire order. */
export const GRADING_RESULT_KEYS = [
  "responseId",
  "senseId",
  "isCorrect",
  "gradeScore",
  "gradeFeedback",
  "masteryBefore",
  "masteryAfter",
  "renderFormat",
  "reveal",
] as const

/**
 * Whether a value is a usable grading result.
 *
 * Checks the fields the verdict is actually built from and tolerates extra
 * keys, so adding a field to the Python payload cannot reject a snapshot a
 * client already understands. A *renamed* field does fail here, which is the
 * whole point.
 */
export function isGradingResultPayload(
  value: unknown,
): value is GradingResultPayload {
  if (!value || typeof value !== "object") return false
  const payload = value as Record<string, unknown>
  return (
    typeof payload.responseId === "string" &&
    typeof payload.senseId === "number" &&
    typeof payload.isCorrect === "boolean" &&
    typeof payload.gradeScore === "number" &&
    (payload.gradeFeedback === null || typeof payload.gradeFeedback === "string") &&
    (payload.masteryBefore === null || typeof payload.masteryBefore === "number") &&
    (payload.masteryAfter === null || typeof payload.masteryAfter === "number") &&
    typeof payload.renderFormat === "string" &&
    (payload.reveal === null || typeof payload.reveal === "object")
  )
}

/**
 * The channel namespace a durable task is published on.
 *
 * Emitted so the subscriber builds the same channel the publisher does. Low
 * risk today because authorization never parses ownership out of a channel
 * name — the subscribe proxy looks up the interest row and fails closed — but
 * a mismatch means every event lands somewhere no client is listening.
 */
export const ASYNC_TASK_NAMESPACE = "async"
