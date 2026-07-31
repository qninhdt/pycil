import { expect, test } from "../fixtures/test"

/**
 * Sign-in, the signed-out guard, and the anonymous read path.
 *
 * The authenticated half of this file rides the session sealed in global setup, so
 * what it proves is that the app's own `lib/auth/session.ts` unseals a cookie the
 * `dev_identity` CLI's token was put into. Nothing here stubs `getSession`: if the
 * sealing or the unsealing broke, this file fails first, which is why it is
 * asserted explicitly rather than left implicit in every other spec.
 */

test.describe("an authenticated viewer", () => {
  test("lands on Today rather than being bounced to sign-in", async ({ page }) => {
    await page.goto("/")

    // The sealed cookie is a real session: no redirect to /login.
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  })

  test("is recognised as the seeded identity", async ({ page, fixture }) => {
    await page.goto("/settings")
    await expect(page).not.toHaveURL(/\/login/)

    // The account screen names the signed-in address. This is the assertion that
    // proves the *identity* survived the seal, not merely that some session did:
    // a cookie sealed with the right password but the wrong user would pass a
    // redirect check and fail here.
    await expect(page.getByText(fixture.user.email, { exact: false }).first()).toBeVisible()
  })

  test("reaches every signed-in destination", async ({ page }) => {
    for (const path of ["/", "/library", "/progress", "/settings"]) {
      await page.goto(path)
      await expect(page, `${path} should not redirect to sign-in`).not.toHaveURL(
        /\/login/,
      )
    }
  })

  test("is sent away from the sign-in screen rather than shown it again", async ({
    page,
  }) => {
    // The other direction of the guard (`proxy.ts`, the `AUTH_ONLY` branch), and the
    // only one the rest of this file cannot see: every assertion above is "did not
    // land on /login", which a proxy that simply never redirected would also satisfy.
    // Offering sign-in to someone already signed in is the specific confusion this
    // branch exists to prevent.
    await page.goto("/login")

    // Asserted as the root path itself, not merely as "not /login": the redirect
    // target is part of the contract, and landing anywhere else would still satisfy
    // a negative check.
    await expect(page).toHaveURL(/^https?:\/\/[^/]+\/$/)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  })
})

test.describe("an anonymous visitor", () => {
  test("is offered sign-in as a navigation, not a handler", async ({
    anonymousPage,
  }) => {
    await anonymousPage.goto("/login")

    // A real anchor to the BFF route: sign-in is a navigation that redirects to
    // the provider, not a click handler — a handler would break middle-click and
    // "open in new tab", and would leave nothing for a crawler or a keyboard user
    // to act on.
    //
    // Matched by role "button" rather than "link" on purpose. The design system's
    // `Button` renders through Base UI with `render={<a href=…/>}`, which emits an
    // `<a>` carrying an explicit `role="button"` — so the accessible role is
    // button while the element is an anchor. Asserting `href` on it is what
    // proves the navigation is real; the role only locates it.
    const continueControl = anonymousPage.getByRole("button", { name: /continue/i })
    await expect(continueControl).toHaveAttribute("href", "/api/auth/login")
  })

  test("reads a public deck without an account and is not redirected", async ({
    anonymousPage,
    fixture,
  }) => {
    await anonymousPage.goto(`/library/${fixture.publicDeckId}`)

    // Not redirected. This is the specific regression the plan calls out: a
    // public link that bounces an anonymous reader to sign-in defeats the point
    // of publishing it.
    await expect(anonymousPage).not.toHaveURL(/\/login/)

    // Real content, not an empty shell: the deck's own name renders.
    await expect(
      anonymousPage.getByRole("heading", { name: fixture.publicDeckName }),
    ).toBeVisible()

    // And a call to action, because reading is allowed while studying is not.
    // Same anchor-with-button-role shape as the login screen's Continue control.
    await expect(
      anonymousPage.getByRole("button", { name: /sign in/i }).first(),
    ).toBeVisible()
  })

  test("reads a public sense link without an account", async ({
    anonymousPage,
    fixture,
  }) => {
    await anonymousPage.goto(`/w/${fixture.publicSenseId}`)

    await expect(anonymousPage).not.toHaveURL(/\/login/)
    // The headword is the assertion that would have failed before phase 2, when
    // the deck row rendered a definition with no word attached to it.
    await expect(anonymousPage.getByRole("heading", { level: 1 })).toBeVisible()
  })

  test("is sent to sign-in for anything that needs an account", async ({
    anonymousPage,
  }) => {
    await anonymousPage.goto("/settings")

    // Settings is the caller's own account, so it must be guarded, and the
    // `from` parameter is what carries them back after signing in.
    await expect(anonymousPage).toHaveURL(/\/login/)
    await expect(anonymousPage).toHaveURL(/from=/)
  })
})
