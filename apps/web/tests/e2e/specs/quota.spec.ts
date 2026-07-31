import { readSessionState } from "../fixtures/api"
import { clearGradingQuota, setGradingQuotaUsed } from "../fixtures/quota"
import {
  answerKey,
  FREE_TEXT_ANSWER,
  showing,
  startSession,
  waitForSettled,
  walkSession,
} from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * The grading budget, at its boundary.
 *
 * `take_grading_slot` (`learning/session_store.py`) allows twenty rubric grades per
 * learner per five-minute window and refuses the twenty-first with
 * `answer_grading_quota_exceeded`. Only rubric-graded formats spend a slot: a
 * single-choice answer is scored in-request and never reaches the guard.
 *
 * What matters is not the refusal but what the session does next. A spent budget is
 * a deliberate limit, not a fault, so the question has to stay on screen with the
 * reason stated and the session has to remain usable. The reducer's branch is already
 * unit-tested (`tests/unit/session-machine.test.ts`); what only the real stack can
 * show is that the API's guard, the wire code, the notice, and the following `/next`
 * agree with each other.
 */

test.describe("the grading quota", () => {
  test("refuses a rubric grade without wedging the session", async ({
    learnerPage,
    returningLearner,
    fixture,
  }) => {
    test.skip(
      !fixture.supplyWarmed,
      "Needs retrievable assessments; the quota only applies to rubric-graded formats.",
    )
    test.setTimeout(900_000)

    // `returningLearner` because free-text is the only format that takes a slot, and
    // it exists only at difficulty 3-4 — which `sample_requested_level` requests for
    // a due, high-mastery sense and never for a new one.
    //
    // The budget is spent *before* the session starts so the first rubric answer of
    // the walk is the one that gets refused. Seeded rather than earned: twenty live
    // model grades would take minutes to observe a branch that turns on one integer,
    // and would drain the budget every other spec in this run shares.
    await setGradingQuotaUsed(returningLearner.userId, { remaining: 0 })

    try {
      const sessionId = await startSession(learnerPage, returningLearner.deckId)

      const walk = await walkSession(learnerPage, {
        stopAt: "free_text",
        key: answerKey(fixture.senses),
      })

      expect(
        walk.ended,
        "no free-text question was served, so the quota guard was never reached",
      ).toBe("free_text")

      // --- the refusal, stated to the learner --------------------------------
      //
      // The exact sentence from the taxonomy (`lib/api/error-taxonomy.ts`), not a
      // paraphrase: the point of that table is that a learner reads a reason rather
      // than a code, so the wording is the assertion.
      await expect(
        learnerPage.getByText(/reached today's limit for graded answers/i),
      ).toBeVisible({ timeout: 60_000 })

      // The question is still there. A refused grade must not blank the screen or
      // advance past the question — the learner has answered nothing yet.
      await expect(
        learnerPage.getByRole("button", { name: /^submit$/i }),
      ).toBeVisible()

      // The count as it stands with the refusal already applied. Not asserted against
      // zero: the walk answered the rule-graded questions ahead of this one, and those
      // legitimately count. This is the baseline for the increment below, which is what
      // actually proves the refusal recorded nothing.
      const refused = await readSessionState(returningLearner.token, sessionId)

      // --- and the session is still usable ----------------------------------
      //
      // The budget is released and the same question submitted again. This is the
      // half the plan cares about: a quota rejection that left the session wedged
      // would strand the learner on a question they cannot get past.
      await clearGradingQuota(returningLearner.userId)

      // Refilled, not merely resubmitted. The runner keys the draft answer by
      // `senseId:questionId` and derives the field's value from that key
      // (`session-runner.tsx`), so a rejected submission leaves the question on
      // screen with an empty box — and Submit disabled, since it refuses an empty
      // answer. Clicking without typing again waits on a control that never enables.
      const answer = learnerPage.getByRole("textbox", { name: /your answer/i })
      await expect(answer).toBeVisible()
      await answer.fill(FREE_TEXT_ANSWER)

      await learnerPage.getByRole("button", { name: /^submit$/i }).click()

      // Now it grades. Rubric grading is asynchronous, so this waits for the verdict
      // to arrive over SSE exactly as the study spec does.
      await expect(
        learnerPage.getByRole("button", { name: /^continue$/i }),
      ).toBeVisible({ timeout: 300_000 })

      // Exactly one more than before the retry. Greater-than would also pass if the
      // refused attempt had been recorded and then the retry added a second row, which
      // is the specific double-count a consume-once bind exists to prevent.
      const graded = await readSessionState(returningLearner.token, sessionId)
      expect(
        graded.answersTotal,
        "the retried answer was not recorded exactly once, so either the refusal " +
          "counted or the retry double-inserted",
      ).toBe(refused.answersTotal + 1)

      // The session continues from there rather than ending at the refusal.
      await learnerPage.getByRole("button", { name: /^continue$/i }).click()
      await waitForSettled(learnerPage)
      expect(
        await showing(learnerPage, /still waiting on the server/i, "heading"),
        "the session stalled after a quota rejection",
      ).toBe(false)
    } finally {
      // Cleared on every path. The key carries a 300s TTL, so a spec that failed
      // mid-way would otherwise hand a spent budget to whatever runs next.
      await clearGradingQuota(returningLearner.userId)
    }
  })
})
