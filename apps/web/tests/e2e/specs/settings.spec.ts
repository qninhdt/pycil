import { apiCall } from "../fixtures/api"
import { expect, test } from "../fixtures/test"

/**
 * The session-shape form, round-tripped through the real API.
 *
 * These two values used to live in `deck_attributes.settings` as JSONB, per deck.
 * That meant the same learner got a different session length depending on which deck
 * they opened, and a session started on a *folder* ignored them entirely because a
 * folder has no settings row — so a configured value applied about half the time.
 * They are now one row per learner (`user_learning_settings`, migration 0019) behind
 * `GET`/`PATCH /v1/me/learning-settings`.
 *
 * What this spec is for is the round trip: typed in, persisted, and read back by a
 * *different* reader than the one that wrote it. The planner's use of these numbers is
 * deliberately not re-asserted here — `apps/api/tests/learning/` owns that at the layer
 * where it is cheap and exact, and re-proving it through a browser would be slower and
 * less precise for the same claim.
 */

/** The form's own bounds, matching the DTO and the table's CHECK constraints. */
const MIN = 1
const MAX = 100

test.describe("session shape settings", () => {
  test("round-trips through the form and survives a reload", async ({
    learnerPage,
    learner,
  }) => {
    await learnerPage.goto("/settings")

    const words = learnerPage.getByLabel("Words per session")
    const perRound = learnerPage.getByLabel("Questions per round")

    // The effective values are rendered, never an empty field. A learner with no row
    // gets the policy defaults resolved server-side (`planning.settings_for_user`),
    // precisely so no client has to reimplement them to show a number.
    await expect(words).not.toHaveValue("")
    await expect(perRound).not.toHaveValue("")

    // Chosen to differ from the defaults (10 and 8) so a form that silently ignored
    // the write would fail here rather than coincidentally agree.
    const nextWords = "7"
    const nextPerRound = "3"

    const save = learnerPage.getByRole("button", { name: /^save$/i })

    // Retried as a unit, for the same hydration reason as the bounds test below: these
    // inputs are controlled, so a `fill` landing before hydration leaves the typed text
    // on screen while React state still holds the server value — and Save, which is
    // driven by state, never enables.
    await expect(async () => {
      await words.fill("")
      await words.fill(nextWords)
      await perRound.fill("")
      await perRound.fill(nextPerRound)
      await expect(save, "Save should enable once a value changes").toBeEnabled({
        timeout: 1_000,
      })
    }).toPass({ timeout: 30_000 })

    await save.click()

    // The confirmation the learner sees.
    await expect(learnerPage.getByText(/session settings saved/i)).toBeVisible()

    // Save disables again: the form re-seeds from the response, so "nothing to save"
    // is judged against what the server confirmed rather than against what was typed.
    await expect(save).toBeDisabled()

    // --- persisted, not merely echoed ----------------------------------------
    //
    // A reload re-reads through the server component, so this is the assertion that
    // the row was actually written rather than held in component state.
    await learnerPage.reload()
    await expect(learnerPage.getByLabel("Words per session")).toHaveValue(nextWords)
    await expect(learnerPage.getByLabel("Questions per round")).toHaveValue(nextPerRound)

    // --- and the API agrees with the screen ----------------------------------
    //
    // Read directly, as a second reader. The form could round-trip perfectly against a
    // cache while the row said something else, and the planner reads the row.
    const { body } = await apiCall<{
      targetWordsPerSession: number
      maxQuestionsPerRound: number
    }>("/v1/me/learning-settings", { token: learner.token, expectStatus: [200] })

    expect(body.targetWordsPerSession).toBe(Number(nextWords))
    expect(body.maxQuestionsPerRound).toBe(Number(nextPerRound))
  })

  test("refuses an out-of-range value in the form rather than sending it", async ({
    learnerPage,
  }) => {
    await learnerPage.goto("/settings")

    const words = learnerPage.getByLabel("Words per session")
    const save = learnerPage.getByRole("button", { name: /^save$/i })

    // Cleared before each attempt, and retried until React acknowledges it.
    //
    // Two things conspire here. The input is controlled, so a `fill` that lands before
    // hydration is a no-op with a visible result: the DOM keeps the typed text while
    // state still holds the server value. And React's value tracker then records that
    // typed text as the current value at hydration — so re-filling the *same* number
    // is deduped as "no change" and `onChange` never fires, leaving the retry stuck
    // forever. Filling empty first makes each attempt a genuine change. WebKit
    // hydrates slowly enough to hit this every run; Chromium hid it.
    await expect(async () => {
      await words.fill("")
      await words.fill(String(MAX + 1))
      // Stated as a sentence, and Save is blocked. The API would refuse this too, but
      // a learner should read a bound rather than an error code — so the client
      // refuses first and the API stays the backstop.
      await expect(
        learnerPage.getByText(new RegExp(`from ${MIN} to ${MAX}`, "i")),
      ).toBeVisible({ timeout: 1_000 })
    }).toPass({ timeout: 30_000 })

    await expect(save).toBeDisabled()

    // The field is marked invalid for assistive technology, not only visually.
    await expect(words).toHaveAttribute("aria-invalid", "true")
  })

  test("the API is the backstop for a value the form would not send", async ({
    learner,
  }) => {
    // Straight at the endpoint, bypassing the form. The client's bounds are an
    // ergonomic, not the guarantee: the planner divides its work by both numbers, so a
    // zero arriving from any caller would build a session with nothing in it.
    const { status } = await apiCall("/v1/me/learning-settings", {
      method: "PATCH",
      token: learner.token,
      body: { targetWordsPerSession: 0, maxQuestionsPerRound: 8 },
      expectStatus: [422],
    })
    expect(status).toBe(422)
  })
})
