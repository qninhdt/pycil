import { readSessionState } from "../fixtures/api"
import { restartRealtime } from "../fixtures/realtime"
import {
  answerKey,
  showing,
  startSession,
  waitForSettled,
  walkSession,
} from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * A rubric grade that settles across a dropped subscription.
 *
 * `study.spec.ts` proves the happy path: the worker's verdict reaches the browser
 * over Centrifugo without a reload. This proves the recovery, which is a different
 * mechanism entirely. If the socket dies while the worker is still grading, the
 * verdict is published to a client that is not listening — so the client has to
 * re-subscribe and rebuild the verdict from the snapshot it then receives
 * (`lib/study/grade-snapshot.ts`, `lib/realtime/use-task-snapshot.ts`).
 *
 * The distinction matters because the screen looks identical in the failure case
 * right up until it doesn't: a client that reconnects but never replays sits on
 * "being marked" forever, holding a grade the server applied minutes earlier.
 *
 * Centrifugo is genuinely restarted rather than having its route blocked in the
 * browser. Blocking a request would exercise reconnect against a server that never
 * went away; the claim here is that state missed during a real outage is recovered.
 */

test.describe("realtime recovery", () => {
  test("a pending grade settles after Centrifugo restarts", async ({
    learnerPage,
    returningLearner,
    fixture,
  }) => {
    test.skip(
      !fixture.supplyWarmed,
      "Needs retrievable assessments; only a rubric-graded answer defers to SSE.",
    )
    test.setTimeout(900_000)

    // `returningLearner` for the same reason as the free-text spec: free text exists
    // only at difficulty 3-4, which `sample_requested_level` requests for a due,
    // high-mastery sense and never for a new one. Against a deck of new words this
    // would serve nothing but single-choice, which is graded in-request and never
    // touches the realtime path at all.
    const sessionId = await startSession(learnerPage, returningLearner.deckId)

    const walk = await walkSession(learnerPage, {
      stopAt: "free_text",
      key: answerKey(fixture.senses),
    })

    // An assertion, not a skip. A run that serves no rubric-graded question means the
    // schedule seeding or the sampler changed, which is a finding rather than a
    // reason to pass quietly.
    expect(
      walk.ended,
      "no free-text question was served, so the realtime path was never exercised",
    ).toBe("free_text")

    // --- the outage, taken while the grade is in flight ----------------------
    //
    // Restarted immediately after submission. The worker keeps grading throughout —
    // it talks to Redis and Postgres, not to Centrifugo's socket — so the verdict is
    // very likely published while the browser has no subscription, which is exactly
    // the window being tested.
    //
    // If the grade happens to settle before the restart lands, the spec still holds:
    // the assertion below is that the verdict arrives, and arriving early is not a
    // failure. What would fail is never arriving.
    await restartRealtime()

    // The verdict, after the socket came back. No reload and no polling by this spec:
    // the only way a Continue appears here is the client re-subscribing and the
    // snapshot carrying the grade it missed.
    await expect(
      learnerPage.getByRole("button", { name: /^continue$/i }),
      "the verdict never arrived after Centrifugo restarted, so the client either " +
        "did not re-subscribe or the replayed snapshot did not carry the grade",
    ).toBeVisible({ timeout: 300_000 })

    // Recorded server-side, which is the half the screen cannot prove. A client that
    // invented a verdict locally would satisfy the assertion above.
    const state = await readSessionState(returningLearner.token, sessionId)
    expect(
      state.answersTotal,
      "the answer was not recorded server-side",
    ).toBeGreaterThan(0)

    // And the session is still usable rather than stalled on the recovered question.
    await learnerPage.getByRole("button", { name: /^continue$/i }).click()
    await waitForSettled(learnerPage)
    expect(
      await showing(learnerPage, /still waiting on the server/i, "heading"),
      "the session stalled after the realtime outage",
    ).toBe(false)
  })
})
