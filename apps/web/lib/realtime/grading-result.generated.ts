/**
 * Generated from packages/shared-py/shared/realtime/payloads.py by scripts/extract-realtime-contracts.py. Do not edit.
 *
 * Source fingerprint: e07921786315
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

/**
 * The channel namespace a durable task is published on.
 *
 * Emitted so the subscriber builds the same channel the publisher does. Low
 * risk today because authorization never parses ownership out of a channel
 * name — the subscribe proxy looks up the interest row and fails closed — but
 * a mismatch means every event lands somewhere no client is listening.
 */
export const ASYNC_TASK_NAMESPACE = "async"
