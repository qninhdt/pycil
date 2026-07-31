import { readSessionState } from "../fixtures/api"
import {
  answerKey,
  expectRecapFigure,
  showing,
  startSession,
  waitForSettled,
  walkSession,
} from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * The study loop, end to end against the real stack.
 *
 * This is the file the whole harness exists for. Everything it asserts depends on
 * behaviour that only appears when the API, the worker, Redis and Centrifugo are
 * all running: a question is prepared asynchronously by a live model, a verdict for
 * a free-text answer arrives over SSE rather than in the response, and a recap is
 * read back from a durable row after the live session state has been deleted.
 *
 * **Every spec studies its own learner's deck.** Scheduling state is keyed
 * `(user_id, sense_id)`, so a session leaves every sense it touched scheduled for a
 * later day. Sharing one learner made these specs order-dependent — the first to run
 * passed and the rest opened on "Nothing due right now", which looks exactly like a
 * planner bug. Hence `learnerPage`/`learner` rather than `page`/`fixture`.
 *
 * The waits, the answer key and the walk live in `fixtures/study-runner.ts` because
 * the quota and realtime-recovery specs need them too.
 */

test.describe("the study loop", () => {
  test("runs a session to exhaustion, crossing a round boundary", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(
      !fixture.supplyWarmed,
      "No assessment was retrievable when the fixture was built, so this deck can " +
        "only serve exposure cards. Check LEXI_LLM_* and the worker logs.",
    )
    // Long, and honestly so: a rubric-graded answer is marked by a live model.
    test.setTimeout(900_000)

    await startSession(learnerPage, learner.deckId)
    const walk = await walkSession(learnerPage, { key: answerKey(fixture.senses) })

    // A stall is a real defect for this spec, not latency to be skipped over.
    // Level-1 supply holds exactly the two questions a sense needs, so a walk that
    // answers correctly must reach the recap; stalling means either an answer was
    // marked wrong (opening a retry no question can satisfy) or supply regressed.
    expect(walk.ended, "the session did not reach its recap").toBe("complete")
    await expect(
      learnerPage.getByRole("heading", { name: /session complete/i }),
    ).toBeVisible()

    // The session did real work rather than only turning over exposure cards.
    expect(walk.assessments, "no assessment was ever served").toBeGreaterThan(0)
    // The recap's own figures agree that answers were recorded.
    await expectRecapFigure(learnerPage, "Answered")
  })

  test("recap survives a reload, read from the durable summary", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(!fixture.supplyWarmed, "Needs a session that can reach exhaustion.")
    test.setTimeout(900_000)

    const sessionId = await startSession(learnerPage, learner.deckId)
    const walk = await walkSession(learnerPage, { key: answerKey(fixture.senses) })

    expect(walk.ended).toBe("complete")

    // The assertion. Reaching exhaustion deletes the live Redis namespace, so a
    // reload can only render this screen from the persisted summary row. If the
    // recap were held in component state, this is where it would vanish.
    await learnerPage.reload()
    await expect(learnerPage).toHaveURL(new RegExp(`/study/${sessionId}`))
    await expect(
      learnerPage.getByRole("heading", { name: /session complete/i }),
    ).toBeVisible({ timeout: 60_000 })
    await expectRecapFigure(learnerPage, "Answered")
  })

  test("a free-text verdict arrives over SSE, and survives a reload mid-grade", async ({
    learnerPage,
    returningLearner,
    fixture,
  }) => {
    test.skip(!fixture.supplyWarmed, "Needs retrievable assessments.")
    test.setTimeout(900_000)

    // `returningLearner`, not `learner`, and that is the whole reason this spec can
    // run at all. Free-text exists only at difficulty 3-4 (`use_in_sentence`), and a
    // *new* sense always requests `ASSESSMENT_FLOOR = 1` (`learning/planning.py`),
    // where the only generators are `contextual_mcq` and `definition_mcq`. Levels 3-4
    // come solely from `sample_requested_level` (`learning/policy.py`), which applies
    // to *due* senses with accumulated mastery. Against a deck of new words this spec
    // skipped every single run while claiming it was merely unlucky — the async
    // grading path, the most fragile path in the product, was never covered.
    const sessionId = await startSession(learnerPage, returningLearner.deckId)

    // Walk until a free-text question turns up: it is the only rubric-graded format,
    // and therefore the only one whose verdict is not in the response.
    const walk = await walkSession(learnerPage, {
      stopAt: "free_text",
      key: answerKey(fixture.senses),
    })

    // An assertion rather than a skip. The top mastery band's profile is
    // `{2: 0.10, 3: 0.50, 4: 0.40}` across two checkpoints on four senses, so a run
    // that serves no level 3-4 question at all means the schedule seeding or the
    // sampler changed — which is a finding, not a reason to pass quietly.
    expect(
      walk.ended,
      "no free-text question was served to a due, high-mastery learner: check " +
        "markSensesDue and sample_requested_level",
    ).toBe("free_text")

    // --- the verdict arrives over SSE, with no reload --------------------------
    //
    // The pending state is real: the response carried a task id, not a verdict. Its
    // absence would mean the answer was graded synchronously, which for a rubric
    // format would be a contract change rather than a passing test.
    //
    // Tolerated rather than required, because the race is legitimate — the worker
    // graded in ~4s in a recorded run, and a fast grade can settle before this
    // assertion looks. What is *not* tolerated is never settling at all.
    if (!(await showing(learnerPage, /^continue$/i, "button"))) {
      // "Marking" is the tag; the prose says "is being marked". Matching the status
      // text rather than the badge keeps this off badge wording.
      await expect(learnerPage.getByText(/being marked/i).first()).toBeVisible({
        timeout: 30_000,
      })
    }

    // The actual SSE assertion: no reload, no polling by this spec. The verdict can
    // only reach the screen through the realtime subscription, so a Continue here is
    // proof the worker's grade travelled Centrifugo -> subscribe proxy -> client.
    await expect(learnerPage.getByRole("button", { name: /^continue$/i })).toBeVisible({
      timeout: 300_000,
    })

    // --- and the graded answer is durable across a reload -----------------------
    //
    // Deliberately *not* asserting that the verdict panel returns. It does not, and
    // the code says why: `pendingTaskId` lives in the reducer (`session-machine.ts`
    // `applyGrade`), `initialSessionState` takes no parameter to restore it, and the
    // session read carries `awaitingGrade` but no task id (`learning/schemas.py`).
    // So a reload legitimately re-enters `advancing` and serves the next question.
    //
    // `lib/study/grade-snapshot.ts` overstates this in its header — "a reload
    // re-subscribes and the replayed snapshot rebuilds the same verdict" holds for a
    // dropped socket, not for a reload. An earlier version of this spec believed the
    // comment and failed against correct behaviour.
    //
    // What must hold is that nothing was lost: the answer was recorded server-side
    // before the reload, so the session resumes rather than re-asking the same
    // question or erroring.
    await learnerPage.reload()
    await expect(learnerPage).toHaveURL(new RegExp(`/study/${sessionId}`))
    await waitForSettled(learnerPage)

    // The recorded answer is the server's, so it is read back from the server rather
    // than inferred from the screen: `answersTotal` counts submissions, and a grade
    // that vanished with the tab would leave it at zero.
    const state = await readSessionState(returningLearner.token, sessionId)
    expect(
      state.answersTotal,
      "the free-text answer was not recorded server-side, so the reload lost it",
    ).toBeGreaterThan(0)
  })

  test("a live session is resumed by its own URL rather than restarted", async ({
    learnerPage,
    learner,
  }) => {
    const sessionId = await startSession(learnerPage, learner.deckId)

    // The runner is keyed by session id, so a reload must land on the same session. A
    // second POST would produce a different id and abandon the first session holding
    // its reserved deliveries.
    await learnerPage.reload()
    await expect(learnerPage).toHaveURL(new RegExp(`/study/${sessionId}`))
    await waitForSettled(learnerPage)

    // And the launch screen, revisited, does not silently resume: it offers to start,
    // because creating a session is an explicit action.
    await learnerPage.goto(`/study/start/${learner.deckId}`)
    await expect(
      learnerPage
        .getByRole("button", { name: /start studying/i })
        .or(learnerPage.getByRole("heading", { name: /nothing due right now/i })),
    ).toBeVisible()
  })

  test("leaving a session is confirmed rather than immediate", async ({
    learnerPage,
    learner,
  }) => {
    await startSession(learnerPage, learner.deckId)

    // Escape asks; it does not leave. The whole session is operable from the
    // keyboard, and the exit dialog owns the key while it is open.
    await learnerPage.keyboard.press("Escape")

    const dialog = learnerPage.getByRole("alertdialog").or(learnerPage.getByRole("dialog"))
    await expect(dialog.first()).toBeVisible()

    // Dismissing returns to the session rather than navigating away.
    await learnerPage
      .getByRole("button", { name: /keep studying|cancel/i })
      .first()
      .click()
    await expect(learnerPage).toHaveURL(/\/study\/[0-9a-f]{32}/)
  })
})
