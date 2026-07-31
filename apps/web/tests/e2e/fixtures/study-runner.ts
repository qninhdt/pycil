import type { Page } from "@playwright/test"

import { expect } from "./test"

/**
 * Driving the study runner from a spec: waits, an answer key, and one walk.
 *
 * These live here rather than in `specs/study.spec.ts` because more than one spec
 * needs to get a session moving — the quota boundary and the realtime recovery cases
 * both have to reach a particular question before they can assert anything. Copying
 * the walk into each of them is what produced three identical failures from one wrong
 * label the last time: the same bug had to be found and fixed once per copy.
 *
 * Three rules hold for every caller.
 *
 * **Nothing here polls `/next`.** That endpoint mutates despite being a GET — it
 * reserves a delivery, spends a round slot, and extends the exclusion set — so a
 * spec that drove it directly would strand questions the learner never sees. The
 * screen owns the call; these helpers wait on what it renders.
 *
 * **`preparing` is a normal state, not a failure.** Supply is built by a live model,
 * so treating the preparing panel as an error would fail on latency rather than on a
 * defect. Every wait tolerates it.
 *
 * **Answers must be correct.** Not politeness: level-1 supply holds exactly the two
 * questions a sense needs (`uq_question_content` dedupes on
 * `(sense, type, level, hash)`, and level 1 has only `contextual_mcq` and
 * `definition_mcq`), while `REQUIRED_CHECKPOINTS = 2` distinct questions are required
 * and a served id joins the exclusion set. A wrong answer opens a retry that demands a
 * third level-1 question which cannot exist, and the session stalls.
 */

/**
 * Every label the runner can settle on.
 *
 * Read off the components rather than guessed, because guessing one wrong cost three
 * identical timeout failures: the exposure card's advance control says "Got it"
 * (`components/study/exposure-card.tsx`), not "Continue", and every session opens on
 * an exposure card — so omitting it made every wait block on a page that was working
 * perfectly until the suite timeout.
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
export const TERMINAL_HEADING =
  /session complete|nothing due right now|still waiting on the server/i

/**
 * Waits for the runner to reach a state that is not transient.
 *
 * The transient states are `advancing`, `preparing` and `settling`, all of which
 * render a spinner or a polling panel and resolve on their own. Waiting on the
 * absence of those would be a negative assertion that passes during the first frame;
 * waiting on the presence of a settled affordance is positive and cannot pass early.
 */
export async function waitForSettled(page: Page, timeout = 180_000) {
  const settled = page
    .getByRole("button", { name: new RegExp(`^(${SETTLED.join("|")})$`, "i") })
    .or(page.getByRole("heading", { name: TERMINAL_HEADING }))
  await expect(settled.first()).toBeVisible({ timeout })
}

/** Whether a locator is on screen right now, without failing when it is not. */
export async function showing(page: Page, name: RegExp, role: "button" | "heading") {
  return page
    .getByRole(role, { name })
    .first()
    .isVisible()
    .catch(() => false)
}

/** Opens a fresh session on a deck through the real launch screen. */
export async function startSession(page: Page, deckId: string): Promise<string> {
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

export type Answered =
  | "exposure"
  | "single_choice"
  | "text_span"
  | "free_text"
  | "settled"

/**
 * What each sense in the deck means, keyed by its headword.
 *
 * This is the answer key, and it is built from *public* fixture data rather than
 * read out of the question store. Every multiple-choice stem is "Which word means:
 * <the sense's definition>" and the correct option is the sense's own headword, so
 * matching the definition in the stem to the word that carries it picks the right
 * option without this suite ever seeing a `correct_index`.
 */
export type AnswerKey = { word: string; definition: string; examples: string[] }[]

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
export function answerKey(
  senses: { word?: string | null; definition: string; examples?: string[] | null }[],
): AnswerKey {
  return senses
    .filter(
      (sense): sense is { word: string; definition: string; examples?: string[] | null } =>
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

/** The sentence a free-text answer submits. Exported so a spec can assert on it. */
export const FREE_TEXT_ANSWER =
  "Someone resilient recovers from difficulty rather than being broken by it."

/**
 * Answers whatever question is on screen, whatever its format.
 *
 * The four formats take different inputs — a radio group, a word bank, a textarea,
 * and an exposure card that takes none at all — so a spec that walked a session
 * would otherwise need a branch at every step. Returns what it did, so a caller can
 * assert on the kind of question it happened to get.
 */
export async function answerCurrent(page: Page, key: AnswerKey): Promise<Answered> {
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
    await answer.fill(FREE_TEXT_ANSWER)
    await submit.click()
    return "free_text"
  }

  throw new Error(
    `A submit control is visible but no known input is. Screen text:\n` +
      (await page.locator("main").innerText()),
  )
}

export interface WalkResult {
  exposures: number
  assessments: number
  rounds: number
  /** Why the walk ended, which is what a caller asserts on. */
  ended: "complete" | "stalled" | "nothing_due" | "free_text" | "budget"
}

/**
 * Walks a live session until it ends, or until `stopAt` says to stop.
 *
 * The step budget is bounded rather than `while (true)`. A loop with no ceiling turns
 * a wedged session into a suite that hangs until the outer timeout with nothing said
 * about why.
 */
export async function walkSession(
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
export async function expectRecapFigure(page: Page, label: string): Promise<void> {
  await expect(
    page.locator("main").getByText(label, { exact: true }).first(),
  ).toBeVisible()
}
