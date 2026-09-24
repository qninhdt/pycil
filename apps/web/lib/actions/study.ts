import type { ActionResult } from "@/lib/api/handle-api-error"
import type { GradeResult, NextQuestion, SessionState } from "@/lib/api/types"

import { withClient } from "./authorized-action"

/**
 * The two calls a study session is made of.
 *
 * `advanceSession` wraps a GET that mutates. Read its comment before touching it:
 * the single-flight guard below is not an optimisation, it is what stops a
 * question from being destroyed.
 */

/**
 * One in-flight `/next` per session, keyed by session id.
 *
 * A second caller arriving while the first is outstanding receives the *same*
 * promise instead of issuing a second request. That is what makes React
 * StrictMode's double effect, an impatient double tap, and a component remount
 * harmless.
 *
 * Module scope on the server means this is per server instance, not global. It
 * cannot defend against two browser tabs or two replicas — that would need a
 * distributed lock the API does not offer. It does cover the duplicate sources
 * that actually occur, all of which originate in one client.
 */
const inFlight = new Map<string, Promise<ActionResult<NextQuestion>>>()

/**
 * Advances the session and returns the next question.
 *
 * **This mutates server state despite being served by a GET.** It advances the
 * round counter, reserves a delivery against the chosen sense, and adds the
 * question id to the session's exclusion set. It is not idempotent and accepts no
 * idempotency key.
 *
 * A duplicate call destroys a question. The first call reserves sense S with
 * question Q; the second cannot re-serve S, so it serves a different sense — and Q
 * is now recorded as delivered, excluded from future resolution, and clearable
 * only by answering it. The learner never saw it. Two round slots are spent for
 * one question shown.
 *
 * Consequences for any future change here:
 * - never give this a query key, and never call it from `useQuery`
 * - never retry it automatically
 * - never prefetch the route that calls it
 * - never remove the single-flight guard
 */
export async function advanceSession(
  sessionId: string,
): Promise<ActionResult<NextQuestion>> {
  const existing = inFlight.get(sessionId)
  if (existing) return existing

  const pending = withClient((client) =>
    client.learning.getNextQuestion(sessionId),
  ).finally(() => {
    inFlight.delete(sessionId)
  })

  inFlight.set(sessionId, pending)
  return pending
}

/**
 * Submits an answer.
 *
 * The question id is numeric. An exposure card carries `questionId: null` because
 * it is shown rather than assessed; submitting one is refused with
 * `question_not_assessable`, so callers must not offer a submit control for it.
 *
 * The synchronous response carries the verdict, reveal, and strength/depth
 * transition inline.
 */
export async function submitAnswer(
  sessionId: string,
  questionId: number,
  answer: string,
): Promise<ActionResult<GradeResult>> {
  return withClient((client) =>
    client.learning.submitAnswer({ sessionId, questionId, answer }),
  )
}

/** Starts a session on a deck or folder. */
export async function startSession(nodeId: string) {
  return withClient((client) => client.learning.startSession(nodeId))
}

/**
 * Reads one session. A true read, unlike `advanceSession`.
 *
 * This advances nothing and reserves nothing, so it is safe to call on mount, on
 * reload, and after the session has ended. It answers `status: "live"` from the
 * round store while the session exists and `status: "completed"` from the durable
 * summary afterwards, which is what makes a recap survive a refresh: reaching
 * `exhausted` deletes the live namespace, and only the persisted row is left.
 *
 * A 404 therefore means neither exists — an unknown id, or someone else's.
 */
export async function readSession(
  sessionId: string,
): Promise<ActionResult<SessionState>> {
  return withClient((client) => client.learning.getSession(sessionId))
}
