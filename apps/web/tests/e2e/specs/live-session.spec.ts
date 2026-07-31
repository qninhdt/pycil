import type { Page } from "@playwright/test"

import { readSessionState } from "../fixtures/api"
import { startSession, waitForSettled } from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * Adding a word while a session is open.
 *
 * This is a warning with teeth. Adding a sense bumps the deck's
 * `structural_generation` and that of every ancestor and reverse reference, and the
 * API compares the session's recorded generation on both `/next` and `/answers`
 * (`hierarchy/service.py`, `learning/router.py`). So the add does not merely change
 * what a later session covers — it ends the one in progress, and an answer already on
 * screen is discarded rather than graded.
 *
 * The palette therefore has to know a session is live before it offers the add. Only
 * the study screen knows that, so it publishes to `ui-store` and the palette reads
 * (`lib/stores/ui-store.ts`). That handoff is the thing this spec covers: it spans two
 * screens through a client store, so no unit test and no single-page assertion can see
 * it.
 *
 * It is driven the way a learner reaches it, which is the only way it is reachable at
 * all. The study route renders no shell and therefore no palette, so an add is always
 * started from the library — and stepping out of a session does not end it: the Redis
 * meta stands until the session completes or expires, and the URL resumes it. Leaving
 * and then adding is the actual flow, not a contrivance to make the store observable.
 */

test.describe("adding a word during a live session", () => {
  test("warns before ending the session, and cancelling keeps it", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(
      fixture.seededWords.length === 0,
      "Needs a searchable word that is absent from the deck; adding one the deck " +
        "already holds is idempotent and bumps no generation, so it would assert nothing.",
    )
    test.setTimeout(300_000)

    const sessionId = await startSession(learnerPage, learner.deckId)

    // Out of the session through its own exit, which is a `Link` and therefore a
    // client-side navigation. `page.goto` would reload the document and take the
    // store with it, so the handoff this spec exists to prove would be erased by the
    // act of setting it up.
    await learnerPage.getByRole("button", { name: /leave this session/i }).click()
    await learnerPage.getByRole("button", { name: /^leave$/i }).click()
    await expect(learnerPage).toHaveURL(new RegExp(`/library/${learner.deckId}`))

    // --- the add, from the only screen it can be started from -----------------
    await learnerPage.getByRole("button", { name: /add words/i }).click()
    const palette = learnerPage.getByPlaceholder(/search words, or jump to a screen/i)
    await expect(palette).toBeVisible()

    // A word the library has and this deck does not. Both halves matter: an unknown
    // word offers only the generate option, which creates a sense and touches no
    // deck, and a word already in the deck takes the idempotent early return in
    // `content/service.py` — neither bumps a generation, so neither can warn.
    const absentWord = fixture.seededWords[0]
    await palette.fill(absentWord)

    // Scoped to the results group. The generate fallback also matches an unscoped
    // `option`, and it is the wrong target: `generateWord` adds nothing to a deck.
    const senseOption = learnerPage
      .getByRole("group", { name: /^words$/i })
      .getByRole("option")
      .first()
    await expect(senseOption).toBeVisible({ timeout: 30_000 })
    await senseOption.click()

    // --- the warning ---------------------------------------------------------
    //
    // The wording is the assertion. "Something may change" would be a lie: the
    // session ends, and the dialog says so.
    const dialog = learnerPage.getByRole("alertdialog")
    await expect(dialog).toBeVisible()
    await expect(
      dialog.getByRole("heading", { name: /end your session to add this word/i }),
    ).toBeVisible()
    // It names the deck being studied, so the learner knows which session is at risk.
    await expect(dialog.getByText(new RegExp(learner.deckName, "i"))).toBeVisible()

    // --- cancelling is a real cancel -----------------------------------------
    //
    // Not merely closing the dialog: the session must still be usable afterwards. A
    // guard that warned and then added anyway would pass a dialog-only assertion.
    await dialog.getByRole("button", { name: /keep studying/i }).click()
    await expect(dialog).not.toBeVisible()

    // Proven against the server first, which is where the consequence would live. A
    // completed or scope-changed session reads as anything but `live`.
    const state = await readSessionState(learner.token, sessionId)
    expect(
      state.status,
      "the cancelled add ended the session anyway",
    ).toBe("live")

    // And then resumed, which is the stronger half: a bumped generation makes the
    // next `/next` reject with `session_scope_changed`, so reaching a live control
    // proves the deck's generation is untouched rather than merely that Redis still
    // holds a session.
    await learnerPage.goto(`/study/${sessionId}`)
    await waitForSettled(learnerPage)
    await expect(
      learnerPage
        .getByRole("button", { name: /^(submit|continue|got it|next round)$/i })
        .first(),
    ).toBeVisible()
  })

  test("no warning outside a session", async ({ page, fixture }) => {
    // The counterpart, and the reason this is not just a dialog test. The warning is
    // conditional on a published live session, so it must be absent when there is
    // none — otherwise every add would ask a question with no meaning.
    test.skip(fixture.seededWords.length === 0, "Needs a searchable word to add.")

    await page.goto(`/library/${fixture.deckId}`)

    await page.getByRole("button", { name: /add words/i }).click()
    const palette = page.getByPlaceholder(/search words, or jump to a screen/i)
    await expect(palette).toBeVisible()

    await palette.fill(fixture.seededWords[0])

    const senseOption = page
      .getByRole("group", { name: /^words$/i })
      .getByRole("option")
      .first()
    await expect(senseOption).toBeVisible({ timeout: 30_000 })
    await senseOption.click()

    // No dialog. Asserted as a bounded wait on absence rather than an instant check:
    // the dialog is client-rendered, so an immediate assertion would pass before it
    // had a chance to appear.
    await expect(sessionWarning(page)).toHaveCount(0, { timeout: 5_000 })
  })
})

/** The live-session warning, located the same way in both specs. */
function sessionWarning(page: Page) {
  return page.getByRole("alertdialog", { name: /end your session/i })
}
