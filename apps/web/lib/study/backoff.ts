/**
 * Bounded backoff for the two polled session states.
 *
 * `preparing` and `waiting` are the only states that ask the client to call again,
 * and every call to `/next` mutates. So the delay grows and the attempts are
 * capped: an unbounded retry loop against a mutating endpoint is the one failure
 * mode here that damages server state rather than merely wasting a request.
 *
 * The ceiling is deliberately short. A learner staring at "preparing your next
 * question" for eight seconds has already decided the app is broken, so the
 * schedule reaches its terminal state and offers a retry instead of creeping
 * upwards forever.
 */

/** Delay before attempt `n`, in milliseconds. `n` is 1-based. */
export function backoffDelay(attempt: number): number {
  const step = Math.max(1, attempt)
  return Math.min(BASE_DELAY_MS * 2 ** (step - 1), MAX_DELAY_MS)
}

const BASE_DELAY_MS = 600
const MAX_DELAY_MS = 4_000

/**
 * How many times a polled state re-calls before giving up and asking.
 *
 * Reaching this is not an error: supply generation is asynchronous and can
 * legitimately outlast the schedule. The UI says so and offers to keep waiting.
 */
export const MAX_POLL_ATTEMPTS = 8

export function isPollExhausted(attempt: number): boolean {
  return attempt >= MAX_POLL_ATTEMPTS
}
