import { readSessionState } from "../fixtures/api"
import {
  answerKey,
  expectRecapFigure,
  showing,
  startSession,
  TERMINAL_HEADING,
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

  test("a double advance does not destroy a question", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(!fixture.supplyWarmed, "Needs retrievable assessments to exhaust.")
    test.setTimeout(900_000)

    // `/next` mutates despite being a GET: it advances the round, reserves a delivery
    // against the chosen sense, and adds the question id to the exclusion set. So a
    // duplicate call destroys a question — the second cannot re-serve that sense, and
    // the first question is left recorded as delivered, excluded, and clearable only
    // by answering it. The learner never saw it.
    //
    // Two guards exist: the runner's own ref (`session-runner.tsx`) and the action
    // layer's single-flight map (`lib/actions/study.ts`). The second
    // mechanically. This drives the first through the browser, which is the only place
    // the double invocation it defends against actually originates.
    await startSession(learnerPage, learner.deckId)

    // Every advance control the walk touches — the exposure card's "Got it", the
    // verdict's "Continue", and the round boundary's "Next round" — is invoked twice
    // within one task, so both handler calls land before React re-renders. Doing it
    // across the whole session rather than at the opening screen matters: the exposure
    // card and the round boundary take different paths into the same reservation.
    const walk = await walkSession(learnerPage, {
      key: answerKey(fixture.senses),
      doubleAdvance: true,
    })

    // The consequence a destroyed question produces, asserted rather than the guard
    // itself. A stranded sense can never be re-delivered
    // (`reserve_round_delivery` refuses any sense whose `current_qid` is set), so
    // `/next` returns "preparing" forever and the session never reaches its recap.
    // Completing the walk is therefore proof that no question was lost.
    expect(
      walk.ended,
      "the session stalled instead of reaching its recap, which is what a question " +
        "destroyed by a duplicate /next looks like: the sense is stranded and can " +
        "never be delivered again",
    ).toBe("complete")

    // Guards against a vacuous pass: a walk that answered nothing would also "complete"
    // if the session had no supply, and would have doubled no advance worth doubling.
    expect(walk.exposures + walk.assessments).toBeGreaterThan(0)
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

  test("two rapid Enters submit one answer, not two", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(!fixture.supplyWarmed, "Needs a retrievable assessment to answer.")
    test.setTimeout(600_000)

    // `canSubmit` is read from the phase captured by the current render, and
    // `dispatch` does not update that synchronously — so two Enters landing inside
    // one frame both saw `submitting: false` and both posted.
    //
    // The server is not the thing at risk: `consume_delivered` is a CAS, so exactly
    // one submission wins and the loser is refused `question_not_issued_for_session`.
    // The learner is. The reducer correctly reads that refusal as a desync and
    // re-polls `/next`, which wipes the winner's verdict off the screen before it can
    // be read — the answer counted, the feedback did not arrive, and the question is
    // behind them. So this asserts the verdict *stays*, which is the consequence, and
    // the server-side count, which is the cause.
    await startSession(learnerPage, learner.deckId)

    // Walk to the first question that takes a typed or chosen answer. Exposure cards
    // carry no submit control and are not what this is about.
    for (let step = 0; step < 20; step += 1) {
      await waitForSettled(learnerPage)
      if (await showing(learnerPage, /^submit$/i, "button")) break
      if (await showing(learnerPage, TERMINAL_HEADING, "heading")) break

      const advance = learnerPage.getByRole("button", {
        name: /^(continue|next round|got it)$/i,
      })
      if (!(await advance.first().isVisible().catch(() => false))) break
      await advance.first().click()
    }
    test.skip(
      !(await showing(learnerPage, /^submit$/i, "button")),
      "This session served no assessment before running out of steps.",
    )

    // Single choice is the format a keyboard can answer deterministically: the digit
    // shortcuts pick an option, so the answer is in place before Enter is pressed.
    const options = learnerPage.getByRole("radio")
    test.skip(
      (await options.count()) === 0,
      "The first assessment was not single-choice, which this spec needs to " +
        "answer from the keyboard alone.",
    )
    await options.first().click()

    // Both keydowns dispatched from inside the page, so they reach the handler before
    // React can re-render between them. Two `keyboard.press` calls would not:
    // Playwright awaits each, and the second lands on whatever the first produced.
    await learnerPage.evaluate(() => {
      const press = () =>
        document.dispatchEvent(
          new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
        )
      press()
      press()
    })

    // A verdict, and it stays. A second submission's refusal would send the reducer
    // back to `advancing` and replace this with the next question.
    const carryOn = learnerPage.getByRole("button", { name: /^continue$/i })
    await expect(
      carryOn,
      "no verdict settled, so the answer never landed at all",
    ).toBeVisible({ timeout: 240_000 })
    await learnerPage.waitForTimeout(2_000)
    await expect(
      carryOn,
      "the verdict was replaced by the next question, which is what a second " +
        "submission's `question_not_issued_for_session` refusal does to the screen",
    ).toBeVisible()

    // And the server agrees only one answer was recorded. This is the assertion that
    // would fail on a doubled submit even if the screen happened to settle.
    const sessionId = learnerPage.url().match(/\/study\/([0-9a-f]{32})/)?.[1]
    expect(sessionId, `not on a session URL: ${learnerPage.url()}`).toBeTruthy()
    const state = await readSessionState(learner.token, sessionId!)
    expect(
      state.answersTotal,
      "two Enters recorded two answers, spending a second grading slot on a " +
        "question the learner answered once",
    ).toBe(1)
  })
})
