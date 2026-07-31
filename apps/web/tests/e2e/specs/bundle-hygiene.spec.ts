import { readdir, readFile } from "node:fs/promises"
import path from "node:path"

import { envValue, repoRoot, sessionPassword } from "../fixtures/env"
import { expect, test } from "../fixtures/test"

/**
 * What must never reach the browser.
 *
 * Two surfaces, and the second is the one that actually catches things. Scanning
 * `.next/static` only proves nothing leaked into a *client bundle*; a server
 * component that interpolates a secret into its own output ships it in the RSC
 * payload of a rendered page, where no bundle scan would ever see it. So the
 * authenticated page body is fetched and searched too.
 *
 * The values are read from the same environment the stack runs on rather than
 * hardcoded. A spec asserting on a literal would pass forever after someone
 * rotated a key, which is precisely when a leak check stops being worth having.
 *
 * `dev-login` and `dev-token` are checked here as well. The auth seam for this
 * suite is deliberately a CLI one-shot, not an HTTP route, and the plan forbids
 * such a route from existing at all — so its absence is asserted rather than
 * trusted, in the built output where it would have to appear to be reachable.
 */

/** Every value that is a secret rather than a configuration detail. */
function forbiddenValues(): { name: string; value: string }[] {
  const named = [
    "SESSION_PASSWORD",
    "AUTH_JWT_SECRET",
    "INTERNAL_API_SECRET",
    "CENTRIFUGO_API_KEY",
    "CENTRIFUGO_TOKEN_HMAC_SECRET",
    "CENTRIFUGO_SUBSCRIBE_PROXY_SECRET",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "GOOGLE_CLIENT_SECRET",
    "LEXI_LLM_API_KEY",
  ]

  const values = named
    .map((name) => ({ name, value: envValue(name, "") }))
    // A short value is either unset or something like "1", which would match
    // half the bundle and report a leak that is not one.
    .filter((entry) => entry.value.length >= 8)

  // The session password is read through its own accessor, which enforces the
  // 32-character floor the app boots on, so it is always present.
  values.push({ name: "SESSION_PASSWORD", value: sessionPassword() })

  return values
}

/**
 * The API's internal URL, which is server-only configuration.
 *
 * `PYCIL_API_URL` points at `http://api:8000` — a Docker DNS name that means
 * nothing in a browser. Its presence in a client bundle would say the server-only
 * module holding it got pulled into a client component, which is the mistake this
 * catches even when no credential travels with it.
 */
function forbiddenApiUrl(): string | null {
  const value = envValue("PYCIL_API_URL", "")
  return value.length >= 8 ? value : null
}

async function filesUnder(dir: string): Promise<string[]> {
  const found: string[] = []
  const walk = async (current: string) => {
    let entries
    try {
      entries = await readdir(current, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) await walk(full)
      else found.push(full)
    }
  }
  await walk(dir)
  return found
}

test.describe("bundle hygiene", () => {
  test("no secret reaches the client bundle", async () => {
    const staticDir = path.join(repoRoot, "apps/web/.next/static")
    const files = await filesUnder(staticDir)

    test.skip(
      files.length === 0,
      `No build output at ${staticDir}. Run \`pnpm --filter web build\` first: ` +
        "this spec scans the built client bundle, and an absent build would " +
        "otherwise pass by finding nothing.",
    )

    const secrets = forbiddenValues()
    const apiUrl = forbiddenApiUrl()
    const leaks: string[] = []

    for (const file of files) {
      // Text only. A font or an image cannot carry an interpolated secret, and
      // decoding them as UTF-8 produces byte sequences that match anything.
      if (!/\.(js|mjs|cjs|css|json|txt|map)$/.test(file)) continue
      const content = await readFile(file, "utf8")
      const relative = path.relative(repoRoot, file)

      for (const { name, value } of secrets) {
        if (content.includes(value)) leaks.push(`${name} in ${relative}`)
      }
      if (apiUrl && content.includes(apiUrl)) {
        leaks.push(`PYCIL_API_URL in ${relative}`)
      }
      for (const route of ["dev-login", "dev-token"]) {
        if (content.includes(route)) leaks.push(`${route} route in ${relative}`)
      }
    }

    expect(
      leaks,
      "a server-only value reached the client bundle:\n" + leaks.join("\n"),
    ).toEqual([])
  })

  /**
   * The RSC payload of a page rendered for a signed-in viewer.
   *
   * This is the half a bundle scan cannot do. Server components run with the full
   * environment and their output is serialised into the HTML, so a secret
   * interpolated there travels to the browser inside the page itself — invisible
   * to any check that only reads `.next/static`.
   *
   * The bearer token is the specific value at risk: the session holds it, every
   * server action uses it, and passing it as a prop to a client component would
   * put it in this payload. It is read out of the sealed cookie's own source
   * rather than guessed, so the assertion is about the real token.
   */
  test("no secret reaches the RSC payload of an authenticated page", async ({
    page,
    fixture,
  }) => {
    const secrets = forbiddenValues()
    const apiUrl = forbiddenApiUrl()

    for (const route of ["/", "/library", "/progress", "/settings"]) {
      const response = await page.goto(route)
      expect(response, `${route} returned no response`).not.toBeNull()

      // The served document, not the DOM: the RSC payload is inline script
      // content, and reading `innerText` would miss it entirely.
      const body = (await response!.text()) ?? ""

      // Sanity check that this is the authenticated page rather than a redirect
      // to sign-in, which would contain no secrets for uninteresting reasons.
      expect(page.url(), `${route} redirected to sign-in`).not.toMatch(/\/login/)

      for (const { name, value } of secrets) {
        expect(
          body.includes(value),
          `${name} appears in the RSC payload of ${route}`,
        ).toBe(false)
      }

      if (apiUrl) {
        expect(
          body.includes(apiUrl),
          `PYCIL_API_URL appears in the RSC payload of ${route}`,
        ).toBe(false)
      }

      // The access token itself. Held server-side in the sealed cookie and used
      // by every server action; reaching the payload would mean it was handed to
      // a client component as a prop.
      expect(
        body.includes("Bearer "),
        `an Authorization header value appears in the RSC payload of ${route}`,
      ).toBe(false)
    }

    // And the identity that *is* meant to be visible stays visible, so this spec
    // cannot pass by asserting against empty pages.
    await page.goto("/settings")
    await expect(
      page.getByText(fixture.user.email, { exact: false }).first(),
    ).toBeVisible()
  })
})
