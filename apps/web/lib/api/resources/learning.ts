import type { Fetcher } from "../request"
import type {
  AnswerSubmission,
  GradeResult,
  LearningSettings,
  NextQuestion,
  SessionCreated,
  SessionState,
} from "../types"

/**
 * Sessions, question delivery, and grading.
 *
 * `getNextQuestion` is the one read in this codebase that is not a read. See its
 * comment before treating it like the others.
 */
export function learningResource(fetch: Fetcher) {
  return {
    /**
     * The caller's own session shape.
     *
     * Per learner, not per deck: the same values apply whichever node a session
     * starts from. A read always answers with numbers, because the API resolves an
     * absent row to the policy defaults rather than returning an empty object.
     */
    getLearningSettings: () => fetch<LearningSettings>("/v1/me/learning-settings"),

    /**
     * Sets the caller's session shape.
     *
     * Applies from the next session. A live session carries the plan it was created
     * with, so nothing in progress changes under the learner.
     */
    updateLearningSettings: (data: LearningSettings) =>
      fetch<LearningSettings>("/v1/me/learning-settings", {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    startSession: (nodeId: string) =>
      fetch<SessionCreated>("/v1/sessions", {
        method: "POST",
        body: JSON.stringify({ nodeId }),
      }),

    getSession: (sessionId: string) => fetch<SessionState>(`/v1/sessions/${sessionId}`),

    /**
     * Advances the session and returns the next question.
     *
     * This MUTATES server state despite being a GET. It advances the round
     * counter, reserves a delivery against the sense, and adds the question id to
     * the session's exclusion set. It is not idempotent and takes no idempotency
     * key.
     *
     * A duplicate call destroys a question: the first reserves sense S with
     * question Q, the second cannot re-serve S so it serves a different sense —
     * and Q is now recorded as delivered, excluded from future resolution, and
     * unclearable except by answering it. The learner never saw it. Two round
     * slots are consumed for one question shown.
     *
     * So this must never be a query key, never be retried, never be prefetched,
     * and never run twice concurrently for one session. Its caller in
     * `lib/actions/study.ts` enforces single-flight; that is the only sanctioned
     * entry point.
     */
    getNextQuestion: (sessionId: string) =>
      fetch<NextQuestion>(`/v1/sessions/${sessionId}/next`),

    /**
     * Submits an answer.
     *
     * The question id is numeric. An exposure card carries `questionId: null`
     * because it is shown rather than assessed, and submitting one is rejected
     * with `question_not_assessable`.
     */
    submitAnswer: (submission: AnswerSubmission) =>
      fetch<GradeResult>("/v1/answers", {
        method: "POST",
        body: JSON.stringify(submission),
      }),
  }
}
