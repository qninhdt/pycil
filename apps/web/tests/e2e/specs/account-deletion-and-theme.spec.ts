import { apiCall } from "../fixtures/api"
import { expect, test } from "../fixtures/test"

/**
 * Deleting an account, and the theme, through the browser.
 *
 * Both were uncovered until now, for opposite reasons. Deletion is the one
 * irreversible action in the product, and *that* is why nothing tested it: a spec
 * that deletes the account it is signed in as destroys the fixture every other spec
 * depends on. The `learner` fixture solves it — it mints an identity per spec keyed
 * on the test title, so this one has an account of its own to destroy.
 *
 * The theme went untested for the opposite reason: it looked covered. The
 * `screenshots` project captures every screen in both themes, so both renderings are
 * exercised — but it only writes PNGs, asserts nothing, and is non-gating. A theme
 * that stopped switching entirely would produce twenty identical pairs of images and
 * a green run.
 */

test.describe("account deletion", () => {
  test("refuses to delete until the confirmation is typed exactly", async ({
    learnerPage,
  }) => {
    await learnerPage.goto("/settings")

    await learnerPage.getByRole("button", { name: /^delete account$/i }).click()

    const dialog = learnerPage.getByRole("alertdialog")
    await expect(dialog).toBeVisible()

    const confirm = dialog.getByRole("button", { name: /delete permanently/i })
    // Armed only by the exact literal. A destructive button that is live on open is
    // a button that deletes an account by a misplaced click.
    await expect(confirm).toBeDisabled()

    const input = dialog.getByLabel(/type delete to confirm/i)
    await input.fill("delete")
    await expect(confirm, "a lowercase confirmation armed the delete").toBeDisabled()

    await input.fill("DELETE ")
    await expect(confirm, "a trailing space armed the delete").toBeDisabled()

    await input.fill("DELETE")
    await expect(confirm).toBeEnabled()

    // Dismissing must disarm it. Reopening a dialog that remembered the typed
    // confirmation would present a live delete button to someone who came back to
    // read the consequences.
    await dialog.getByRole("button", { name: /keep my account/i }).click()
    await expect(dialog).not.toBeVisible()

    await learnerPage.getByRole("button", { name: /^delete account$/i }).click()
    await expect(
      learnerPage.getByRole("alertdialog").getByRole("button", {
        name: /delete permanently/i,
      }),
      "reopening the dialog presented an already-armed delete button",
    ).toBeDisabled()
  })

  test("deletes the account, ends the session, and revokes the token", async ({
    learnerPage,
    learner,
  }) => {
    // This spec's own identity, minted for it and used by nothing else. The deletion
    // below is real and irreversible.
    await learnerPage.goto("/settings")
    await learnerPage.getByRole("button", { name: /^delete account$/i }).click()

    const dialog = learnerPage.getByRole("alertdialog")
    await dialog.getByLabel(/type delete to confirm/i).fill("DELETE")
    await dialog.getByRole("button", { name: /delete permanently/i }).click()

    // The action destroys the session and redirects, so arriving at `/login` is the
    // client-side proof that both halves happened.
    await expect(learnerPage).toHaveURL(/\/login/, { timeout: 60_000 })

    // And the guard now sends them there from anywhere, which is what a destroyed
    // cookie means rather than merely a completed redirect.
    await learnerPage.goto("/settings")
    await expect(learnerPage).toHaveURL(/\/login/)

    // The server's side of it, and the assertion that a cleared cookie cannot fake:
    // the account is gone, so its access token no longer identifies anyone. Asserted
    // through the API rather than the screen because a signed-out browser would look
    // identical either way.
    const me = await apiCall("/v1/me", { token: learner.token })
    expect(
      me.status,
      "the account's token still authenticates, so the row was not deleted",
    ).toBe(401)
  })
})

test.describe("the theme", () => {
  test("switches, persists across a reload, and follows the system when asked", async ({
    learnerPage,
  }) => {
    // The app runs `defaultTheme="system"` with `enableSystem`, so the starting point
    // is whatever the OS reports. Pinned to light so "switched to dark" is a real
    // change rather than possibly the value it already had.
    await learnerPage.emulateMedia({ colorScheme: "light" })
    await learnerPage.goto("/settings")

    const root = learnerPage.locator("html")
    await expect(root).not.toHaveClass(/dark/)

    async function choose(label: RegExp) {
      // Two controls write the same preference — the header's and the settings
      // card's — and they are the same component deliberately, so either serves.
      await learnerPage.getByRole("button", { name: /change theme/i }).first().click()
      await learnerPage.getByRole("menuitemradio", { name: label }).click()
    }

    await choose(/^dark$/i)
    // `next-themes` writes the resolved class onto `<html>`, which is what every
    // `dark:` token in the stylesheet keys off. Asserting the class rather than a
    // computed colour keeps this about the mechanism rather than about one palette.
    await expect(root, "choosing Dark did not switch the theme").toHaveClass(/dark/)

    // Stored in the browser, as the card says, so it has to survive a reload. A
    // preference that reset on navigation would be worse than none.
    await learnerPage.reload()
    await expect(root, "the dark preference did not survive a reload").toHaveClass(
      /dark/,
    )

    await choose(/^light$/i)
    await expect(root).not.toHaveClass(/dark/)

    // System is a third state, not the absence of a choice — which is the reason the
    // control is a three-way radio rather than a switch. With the OS reporting dark,
    // choosing System must follow it rather than keep the light it was just set to.
    await learnerPage.emulateMedia({ colorScheme: "dark" })
    await choose(/^system$/i)
    await expect(
      root,
      "System did not follow the OS preference, so the three-way choice collapsed " +
        "to a two-state toggle",
    ).toHaveClass(/dark/)
  })
})
