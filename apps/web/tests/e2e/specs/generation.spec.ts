import { apiCall } from "../fixtures/api"
import { envValue } from "../fixtures/env"
import { expect, test } from "../fixtures/test"

/**
 * The opt-in generation tier.
 *
 * This is the one path that needs a live model to *author* content rather than
 * to grade it, so it is gated on a configured credential and skips with the
 * reason rather than failing on an environment it cannot fix. Question supply and
 * rubric grading work without it; generating a word that the reference dataset
 * has never seen does not.
 *
 * The credential is read from `.env` rather than from `process.env`, because the
 * worker that does the generating gets it through compose from that same file —
 * checking the runner's own environment would report on the wrong process.
 */
function llmConfigured(): boolean {
  return envValue("LEXI_LLM_API_KEY", "").trim().length > 0
}

/**
 * Headwords the reference dataset knows but has not generated senses for.
 *
 * More than one, because a successful run removes its own word from the pool.
 */
const CANDIDATES = [
  "quotidian",
  "sonorous",
  "laconic",
  "ebullient",
  "truculent",
  "perfunctory",
  "sanguine",
  "intrepid",
]

/** Only the two fields this spec reads off a search hit. */
interface WordHit {
  display: string
  senses: unknown[]
}

/**
 * The first candidate that is a known headword with no senses yet.
 *
 * Both halves matter. Senses already present mean generation has run, and
 * `submit_or_join` coalesces on the work key, so the request would join a
 * finished task and settle instantly — green while proving nothing. Requiring an
 * *exact* headword is the other half: a word the dataset has never heard of gets
 * resolved to whatever it is nearest to, so "halcyon" materialises as "halcyon
 * days" and never gains senses under its own name. It would then be picked on
 * every run and join the same finished task forever, which is how this first
 * went green-then-red.
 */
async function firstUngeneratedWord(token: string): Promise<string | null> {
  for (const word of CANDIDATES) {
    const { body } = await apiCall<WordHit[]>(
      `/v1/words/search?q=${encodeURIComponent(word)}`,
      { token, expectStatus: [200] },
    )
    const exact = (body ?? []).find((hit) => hit.display?.toLowerCase() === word)
    if (exact && (exact.senses?.length ?? 0) === 0) return word
  }
  return null
}

test.describe("the generation tier", () => {
  /**
   * The activity centre is the only surface that reports asynchronous work, and
   * nothing reached it before this spec: its trigger dropped the props the popover
   * injects, so a click focused the button and opened nothing. Kept as its own
   * test rather than folded into the generation walk, because a regression here
   * would otherwise read as a generation failure.
   */
  test("the activity centre opens", async ({ learnerPage }) => {
    await learnerPage.goto("/library")
    await learnerPage.getByRole("button", { name: "Activity" }).click()
    await expect(learnerPage.getByText(/nothing running/i)).toBeVisible()
  })

  test("generates a word the dictionary does not have, and settles in Activity", async ({
    learnerPage,
    learner,
  }) => {
    test.skip(
      !llmConfigured(),
      "LEXI_LLM_API_KEY is empty in .env, so the worker has no model to author a " +
        "word with. Set LEXI_LLM_BASE_URL / _API_KEY / _MODEL to run this.",
    )
    // Authoring a full entry is several model calls, not one.
    test.setTimeout(600_000)

    const word = await firstUngeneratedWord(learner.token)
    expect(
      word,
      `every candidate (${CANDIDATES.join(", ")}) already has generated senses, so ` +
        "this spec would join a finished task and assert nothing. Add more " +
        "headwords to CANDIDATES.",
    ).not.toBeNull()

    await learnerPage.goto("/library")
    await learnerPage.keyboard.press("ControlOrMeta+k")
    await learnerPage
      .getByPlaceholder(/search words, or jump to a screen/i)
      .fill(word as string)

    // Scoped to the "Not found" group. Unscoped, a partial match from the word
    // results would win and this would add an existing sense to the deck instead.
    await learnerPage
      .getByRole("group", { name: "Not found" })
      .getByRole("option", { name: new RegExp(`add ${word} to the dictionary`, "i") })
      .click()

    // The app's own signal that the submission returned. Waiting on the palette
    // disappearing is not enough: cmdk hides the list the moment an item is
    // selected, while `onSubmitted` — and the `closeSurface()` inside it — only run
    // once the server action resolves. Opening Activity in that gap gets it closed
    // again by the late `closeSurface`, which is exactly how this first failed.
    await expect(learnerPage.getByText(/adding the word/i)).toBeVisible()

    // The palette closes on submit and the work outlives it, which is the whole
    // reason the task id is registered with the activity store before anything
    // else. Waiting on the toast rather than on the palette disappearing: cmdk
    // hides the list the moment an item is selected, while `onSubmitted` — and the
    // `closeSurface()` inside it — only run once the server action resolves.
    await expect(learnerPage.getByText(/adding the word/i)).toBeVisible()

    await learnerPage.getByRole("button", { name: "Activity" }).click()
    const row = learnerPage.getByRole("listitem").filter({ hasText: word as string })
    await expect(row).toBeVisible()

    // Pending first, settled second. Asserting only the end state would pass on a
    // row that was never anything but "Done", which a joined task would produce.
    // Authoring takes tens of seconds, so this window is wide, not a race.
    await expect(
      row,
      "the row was never pending, so the task settled instantly — which is what " +
        "joining an already-finished generation looks like",
    ).toContainText(/queued|working/i)

    await expect(row).toContainText(/done|failed|expired/i, { timeout: 480_000 })
    await expect(
      row,
      "the generation settled, but not successfully; the row carries the API's own " +
        "error code",
    ).toContainText(/done/i)

    // The row settling is the UI's claim; the dictionary holding the word is the
    // fact behind it. A generation that reported success without materialising
    // senses would satisfy the first and not the second.
    const { body } = await apiCall<WordHit[]>(
      `/v1/words/search?q=${encodeURIComponent(word as string)}`,
      { token: learner.token, expectStatus: [200] },
    )
    const materialised = (body ?? []).find(
      (hit) => hit.display?.toLowerCase() === word,
    )
    expect(
      materialised?.senses?.length ?? 0,
      `Activity reported the generation of "${word}" as done, but the word still ` +
        "has no senses, so nothing was actually written to the dictionary.",
    ).toBeGreaterThan(0)
  })
})
