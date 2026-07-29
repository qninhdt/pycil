import type { Page } from "@playwright/test"

import { readSessionState } from "../fixtures/api"
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
 * Three rules hold throughout.
 *
 * **Every spec studies its own learner's deck.** Scheduling state is keyed
 * `(user_id, sense_id)`, so a session leaves every sense it touched scheduled for a
 * later day. Sharing one learner made these specs order-dependent — the first to run
 * passed and the rest opened on "Nothing due right now", which looks exactly like a
 * planner bug. Hence `learnerPage`/`learner` rather than `page`/`fixture`.
 *
 * **Nothing here polls `/next` itself.** That endpoint mutates despite being a GET,
 * and a duplicate call strands a question the learner never sees. The screen owns
 * the call; the specs wait for what the screen renders.
 *
 * **`preparing` is a normal state, not a failure.** Supply is built by a model, so
 * a spec that treated the preparing panel as an error would fail on latency rather
 * than on a defect. Every wait below tolerates it and waits for the settle.
 */

/**
 * Every label the runner can settle on.
 *
 * Read off the components rather than guessed, because guessing one wrong cost three
 * identical timeout failures: the exposure card's advance control says "Got it"
 * (`components/study/exposure-card.tsx`), not "Continue", and every session opens on
 * an exposure card — so omitting it made every wait here block on a page that was
 * working perfectly until the suite timeout.
 */
const SETTLED = [
  "Submit",
  "Continue",
  "Next round",
  "Got it",
  // The stalled panel. Reached when the poll budget drains before supply lands
  // (`lib/study/session-machine.ts`), which is a designed terminal state rather
  // than a crash — so a walk has to recognise it instead of waiting it out.
  "Keep waiting",
  "Session complete",
  "Nothing due right now",
]

/** The headings that end a session, as opposed to a control that continues one. */
const TERMINAL_HEADING = /session complete|nothing due right now|still waiting on the server/i

/**
 * Waits for the runner to reach a state that is not transient.
 *
 * The transient states are `advancing`, `preparing` and `settling`, all of which
 * render a spinner or a polling panel and resolve on their own. Waiting on the
 * absence of those would be a negative assertion that passes during the first frame;
 * waiting on the presence of a settled affordance is positive and cannot pass early.
 */
async function waitForSettled(page: Page, timeout = 180_000) {
  const settled = page
    .getByRole("button", { name: new RegExp(`^(${SETTLED.join("|")})$`, "i") })
    .or(page.getByRole("heading", { name: TERMINAL_HEADING }))
  await expect(settled.first()).toBeVisible({ timeout })
}

/** Whether a locator is on screen right now, without failing when it is not. */
async function showing(page: Page, name: RegExp, role: "button" | "heading") {
  return page
    .getByRole(role, { name })
    .first()
    .isVisible()
    .catch(() => false)
}

/** Opens a fresh session on a deck through the real launch screen. */
async function startSession(page: Page, deckId: string): Promise<string> {
  await page.goto(`/study/start/${deckId}`)

  // The launch screen is where the session-creating POST lives, precisely so a
  // reload of the runner resumes rather than starting a second session.
  await page.getByRole("button", { name: /start studying/i }).click()

  // The runner's route is keyed by session id, which is what makes a reload
  // resume. Waiting for that URL also proves the POST succeeded.
  await page.waitForURL(/\/study\/[0-9a-f]{32}/, { timeout: 60_000 })
  await waitForSettled(page)

  const match = page.url().match(/\/study\/([0-9a-f]{32})/)
  if (!match) throw new Error(`Not on a session URL: ${page.url()}`)
  return match[1]
}

type Answered = "exposure" | "single_choice" | "text_span" | "free_text" | "settled"

/**
 * What each sense in the deck means, keyed by its headword.
 *
 * This is the answer key, and it is built from *public* fixture data rather than
 * read out of the question store. Every multiple-choice stem is "Which word means:
 * <the sense's definition>" and the correct option is the sense's own headword, so
 * matching the definition in the stem to the word that carries it picks the right
 * option without this suite ever seeing a `correct_index`.
 */
type AnswerKey = { word: string; definition: string; examples: string[] }[]

/**
 * Builds the answer key from the fixture's own sense records.
 *
 * Only senses carrying both a headword and a definition are usable, which is every
 * one the fixture seeds; the filter is there so a partially materialised sense
 * degrades to "answer the first option" rather than throwing mid-walk.
 *
 * Examples come along because a cloze stem *is* one of them with the target blanked,
 * so they are what resolves a typed answer. The dictionary wraps the target in
 * `<t inf="...">…</t>` markup, which is stripped here rather than at the point of
 * use: the stem on screen carries no markup, so a comparison has to be made against
 * plain text.
 */
function answerKey(
  senses: { word?: string | null; definition: string; examples?: string[] | null }[],
): AnswerKey {
  return senses
    .filter((sense): sense is { word: string; definition: string; examples?: string[] | null } =>
      Boolean(sense.word && sense.definition),
    )
    .map((sense) => ({
      word: sense.word,
      definition: sense.definition,
      examples: (sense.examples ?? []).map(stripInflectionMarkup),
    }))
}

/** Drops the dictionary's `<t inf="base">word</t>` wrappers, keeping the word. */
function stripInflectionMarkup(example: string): string {
  return example.replace(/<t\b[^>]*>(.*?)<\/t>/gi, "$1")
}

/**
 * The word a blanked stem is asking for, or null when nothing matches.
 *
 * A cloze stem is a sense's own example with the target replaced by a run of
 * underscores, so the target is recovered by blanking each known example the same way
 * and comparing. Matching on the text either side of the blank rather than on the
 * whole string keeps this working when the stem is punctuated or trimmed differently
 * from the example it came from.
 */
function missingWordFor(stem: string, key: AnswerKey): string | null {
  const normalise = (value: string) => value.toLowerCase().replace(/\s+/g, " ").trim()
  const target = normalise(stem)

  for (const entry of key) {
    for (const example of entry.examples) {
      // The same blanking the generator applies, case-insensitively and on word
      // boundaries so "resilient" does not also blank "resiliently".
      const pattern = new RegExp(`\\b${escapeForRegExp(entry.word)}\\b`, "gi")
      if (!pattern.test(example)) continue
      const blanked = normalise(example.replace(pattern, "_____"))
      // Compared on the halves around the blank: the stem is rendered from the same
      // example but may differ in trailing punctuation.
      const [before, after] = blanked.split("_____")
      if (
        before &&
        after !== undefined &&
        target.startsWith(before.trim()) &&
        (after.trim() === "" || target.includes(after.trim()))
      ) {
        return entry.word
      }
    }
  }

  // The definition is the other identifier a stem can carry: `contextual_mcq` states
  // it outright rather than blanking an example.
  const byDefinition = key.find((entry) =>
    target.includes(entry.definition.toLowerCase().slice(0, 40)),
  )
  return byDefinition?.word ?? null
}

function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Picks the option the deck's own content says is correct.
 *
 * Answering correctly is not politeness, it is a hard requirement. Level-1 supply is
 * capped at two questions per sense — `uq_question_content` dedupes on
 * `(sense, type, level, hash)` and level 1 has only two generators, `contextual_mcq`
 * and `definition_mcq` — while a sense needs `REQUIRED_CHECKPOINTS = 2` *distinct*
 * questions, since a served id joins the session's exclusion set. Two available, two
 * needed: exactly enough, with nothing spare.
 *
 * So a wrong answer is unrecoverable. It opens a retry, the retry demands a third
 * question, no third question can exist, and `/next` polls until the budget drains
 * and the runner stalls. Picking the first radio therefore did not "let the server
 * decide the verdict" — it guaranteed the walk could never reach a recap.
 *
 * Falls back to the first option when the stem matches nothing known, which keeps a
 * new question type from throwing here rather than failing on its own assertion.
 */
async function pickChoice(
  page: Page,
  options: ReturnType<Page["getByRole"]>,
  key: AnswerKey,
): Promise<void> {
  const stem = (await page.locator("main").innerText()).toLowerCase()
  const match = key.find((entry) =>
    stem.includes(entry.definition.toLowerCase().slice(0, 60)),
  )

  if (match) {
    // Exact, case-insensitive: "brittle" must not match a distractor containing it.
    const correct = options.filter({ has: page.getByText(match.word, { exact: true }) })
    if ((await correct.count()) > 0) {
      await correct.first().click()
      return
    }
    // The option text is a sibling of the radio rather than inside it, so fall back
    // to locating the label and clicking that.
    const label = page.getByRole("radio").locator("..").filter({ hasText: match.word })
    if ((await label.count()) > 0) {
      await label.first().click()
      return
    }
  }

  await options.first().click()
}

/**
 * Picks the bank word the deck's own content says is correct.
 *
 * Same reason as `pickChoice`: a wrong answer opens a retry, and a retry needs a
 * question that the level's generators cannot produce a third of.
 */
async function pickFromBank(
  page: Page,
  bank: ReturnType<Page["getByRole"]>,
  key: AnswerKey,
): Promise<void> {
  const stem = await page.locator("main p").first().innerText()
  const word = missingWordFor(stem, key)

  if (word) {
    const correct = bank.getByRole("button", { name: new RegExp(`^${word}$`, "i") })
    if ((await correct.count()) > 0) {
      await correct.first().click()
      return
    }
  }

  await bank.getByRole("button").first().click()
}

/**
 * Answers whatever question is on screen, whatever its format.
 *
 * The four formats take different inputs — a radio group, a word bank, a textarea,
 * and an exposure card that takes none at all — so a spec that walked a session
 * would otherwise need a branch at every step. Returns what it did, so a caller can
 * assert on the kind of question it happened to get.
 */
async function answerCurrent(page: Page, key: AnswerKey): Promise<Answered> {
  const submit = page.getByRole("button", { name: /^submit$/i })
  // "Got it" belongs with the other advance controls: it is the exposure card's only
  // action, and treating its absence as "settled" ended the walk on question one.
  const advance = page.getByRole("button", { name: /^(continue|next round|got it)$/i })

  if (!(await submit.isVisible().catch(() => false))) {
    if (await advance.first().isVisible().catch(() => false)) {
      await advance.first().click()
      return "exposure"
    }
    return "settled"
  }

  // A real radio group: `RadioGroupItem` renders actual radios
  // (`components/study/single-choice-question.tsx`), so role selection works and the
  // digit shortcuts the runner also binds are not needed here.
  const options = page.getByRole("radio")
  if ((await options.count()) > 0) {
    await pickChoice(page, options, key)
    await submit.click()
    return "single_choice"
  }

  const bank = page.getByRole("group", { name: /word bank/i })
  if ((await bank.getByRole("button").count()) > 0) {
    await pickFromBank(page, bank, key)
    await submit.click()
    return "text_span"
  }

  // The same cloze format with no bank: difficulty 3 asks for the word from memory,
  // so `cloze.py` sends `word_bank: []` on purpose and the screen renders a text
  // input instead of toggles. Every level-3 cloze was unanswerable until it did.
  const missing = page.getByRole("textbox", { name: /the missing word/i })
  if (await missing.isVisible().catch(() => false)) {
    const stem = await page.locator("main p").first().innerText()
    const word = missingWordFor(stem, key)
    if (!word) {
      throw new Error(
        `Could not work out the missing word for: "${stem}".\n\n` +
          "The stem is a sense's example with the target blanked, so the fixture's " +
          "examples should resolve it. Check that the sense records carry examples.",
      )
    }
    await missing.fill(word)
    await submit.click()
    return "text_span"
  }

  // Free text is the rubric-graded format, and the only one whose grade does not
  // settle in the response.
  const answer = page.getByRole("textbox", { name: /your answer/i })
  if (await answer.isVisible().catch(() => false)) {
    await answer.fill(
      "Someone resilient recovers from difficulty rather than being broken by it.",
    )
    await submit.click()
    return "free_text"
  }

  throw new Error(
    `A submit control is visible but no known input is. Screen text:\n` +
      (await page.locator("main").innerText()),
  )
}

interface WalkResult {
  exposures: number
  assessments: number
  rounds: number
  /** Why the walk ended, which is what a caller asserts on. */
  ended: "complete" | "stalled" | "nothing_due" | "free_text" | "budget"
}

/**
 * Walks a live session until it ends, or until `stopAt` says to stop.
 *
 * One walk for all three specs that need one. They previously each carried their own
 * copy, which is precisely why a single missing label ("Got it") produced three
 * separate failures: the same bug had to be found and fixed three times.
 *
 * The step budget is bounded rather than `while (true)`. A loop with no ceiling turns
 * a wedged session into a suite that hangs until the outer timeout with nothing said
 * about why.
 */
async function walkSession(
  page: Page,
  {
    key,
    stopAt,
    steps = 80,
  }: { key: AnswerKey; stopAt?: Answered; steps?: number },
): Promise<WalkResult> {
  const seen: WalkResult = { exposures: 0, assessments: 0, rounds: 0, ended: "budget" }

  for (let step = 0; step < steps; step += 1) {
    await waitForSettled(page)

    if (await showing(page, /session complete/i, "heading")) {
      seen.ended = "complete"
      return seen
    }
    if (await showing(page, /nothing due right now/i, "heading")) {
      seen.ended = "nothing_due"
      return seen
    }
    // The poll budget drained before supply landed. Terminal for the walk: clicking
    // "Keep waiting" would restart the same wait, so the caller decides what a stall
    // means for its own assertion.
    if (await showing(page, /still waiting on the server/i, "heading")) {
      seen.ended = "stalled"
      return seen
    }

    // A round boundary is a real screen, not a toast. Crossing it and carrying on is
    // the specific thing the exhaustion spec exists to prove.
    if (await showing(page, /^next round$/i, "button")) {
      seen.rounds += 1
      await page.getByRole("button", { name: /^next round$/i }).click()
      continue
    }

    const kind = await answerCurrent(page, key)
    if (kind === "settled") return seen
    if (kind === "exposure") {
      seen.exposures += 1
      continue
    }

    seen.assessments += 1
    if (kind === stopAt) {
      seen.ended = "free_text"
      return seen
    }

    // A graded answer shows a verdict and a Continue. A rubric-graded one shows the
    // marking panel first and settles into the same place, so both are covered by
    // waiting for Continue rather than by branching here.
    const carryOn = page.getByRole("button", { name: /^continue$/i })
    await expect(carryOn).toBeVisible({ timeout: 240_000 })
    await carryOn.click()
  }

  return seen
}

/**
 * Asserts a recap figure is on screen.
 *
 * Scoped to `main` and matched exactly, which is not fussiness. An unscoped
 * `getByText("Answered")` broke the reload spec in strict mode: during a reload the
 * outgoing document is still attached, so the same `<dt>` resolves twice and Playwright
 * refuses to guess. The recap itself renders one — confirmed from the failure snapshot —
 * so the duplicate was a stale frame rather than a product defect.
 */
async function expectRecapFigure(page: Page, label: string): Promise<void> {
  await expect(
    page.locator("main").getByText(label, { exact: true }).first(),
  ).toBeVisible()
}

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
