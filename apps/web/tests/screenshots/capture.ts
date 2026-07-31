import { mkdir } from "node:fs/promises"
import path from "node:path"

import { startSession, waitForSettled } from "../e2e/fixtures/study-runner"
import { expect, test } from "../e2e/fixtures/test"

/**
 * The review screenshot set: every screen, both themes, both viewports.
 *
 * Evidence, not assertions. A golden-image comparison on a design system this new
 * would fail on every intentional change and tell a reviewer nothing, so nothing
 * here compares against a baseline — each run overwrites the set and a human looks
 * at it. That is also why this is a separate Playwright project rather than a spec:
 * it must not run in CI beside the suites that gate a merge.
 *
 * Both themes are captured through `emulateMedia` rather than by writing
 * `next-themes`' storage key. The app runs `defaultTheme="system"` with
 * `enableSystem`, so the media feature is the real input; seeding localStorage would
 * exercise a path a first-time visitor never takes, and would capture the wrong
 * thing if the resolver ever changed.
 */

/** Where the set lands. Overwritten each run — these are artifacts, not fixtures. */
const OUTPUT_DIR = path.join(process.cwd(), "tests/screenshots/captured")

/**
 * The two sizes the design system was specified against: an iPhone 14 viewport and
 * the desktop width the layout's `max-w-[1120px]` content column was tuned for.
 */
const VIEWPORTS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "desktop", width: 1440, height: 900 },
] as const

const THEMES = ["light", "dark"] as const

/** `light`/`dark` as Playwright's media value. */
type Theme = (typeof THEMES)[number]

interface Shot {
  /** Filename stem, kebab-case; the theme and viewport are appended. */
  name: string
  path: string
}

/**
 * Captures one screen at every theme and viewport combination.
 *
 * `fullPage` because a review set exists to show the whole screen: a viewport-only
 * capture of the settings page would silently omit the half a reviewer most needs
 * to see. The viewport still matters — it decides the layout, the rail versus the
 * tab bar, and which breakpoint's type scale applies.
 */
async function capture(
  page: import("@playwright/test").Page,
  shot: Shot,
  theme: Theme,
): Promise<void> {
  // Both the theme and the motion preference are set on the page rather than
  // through `test.use`. The learner-scoped fixtures build their own
  // `browser.newContext`, so a project-level option would not reach them — and
  // `colorScheme` is the real input here because the app runs
  // `defaultTheme="system"` with `enableSystem`, so seeding `next-themes`'
  // storage key would exercise a path a first-time visitor never takes.
  //
  // Motion off is not cosmetic: a capture taken mid-entry-transition records a
  // half-faded card, so the difference between two runs would be animation timing
  // rather than the design.
  await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" })

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    // Re-goto per viewport rather than resizing in place. These screens branch on
    // `useIsMobile` at mount, so a resize leaves a desktop-mounted tree at a mobile
    // width — which is a rendering no real visitor ever sees.
    await page.goto(shot.path)

    // Waited on the screen's own heading, not on `networkidle`. Every signed-in
    // screen sits inside the shell, which holds an SSE connection to Centrifugo for
    // as long as it is mounted — so the network is never idle and that wait can only
    // ever time out. The `h1` is the thing a capture actually needs: it means the
    // server component resolved and the content is painted.
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
      timeout: 60_000,
    })
    // Fonts specifically, because the set is read for typography. A capture taken
    // before the webfonts swap in records the fallback stack and misreports the
    // design.
    await page.evaluate(() => document.fonts.ready)

    await page.screenshot({
      path: path.join(OUTPUT_DIR, `${shot.name}-${theme}-${viewport.name}.png`),
      fullPage: true,
    })
  }
}

test.beforeAll(async () => {
  await mkdir(OUTPUT_DIR, { recursive: true })
})

for (const theme of THEMES) {
  test.describe(`${theme} theme`, () => {
    test(`signed-in screens (${theme})`, async ({ page, fixture }) => {
      test.setTimeout(180_000)

      const shots: Shot[] = [
        { name: "today", path: "/" },
        { name: "library", path: "/library" },
        { name: "deck", path: `/library/${fixture.deckId}` },
        { name: "sense", path: `/w/${fixture.publicSenseId}` },
        { name: "progress", path: "/progress" },
        { name: "settings", path: "/settings" },
        { name: "study-start", path: `/study/start/${fixture.deckId}` },
      ]

      for (const shot of shots) {
        await capture(page, shot, theme)
      }
    })

    test(`the sign-in screen (${theme})`, async ({ anonymousPage }) => {
      await capture(anonymousPage, { name: "login", path: "/login" }, theme)
    })

    /**
     * The study screen, which needs a live session rather than a URL.
     *
     * Captured from its own learner so the session is real: a screenshot of the
     * launch panel would miss the one screen a learner spends their time on, and
     * the question card is where the mastery ramp, the footer controls and the
     * round indicator all appear at once.
     */
    test(`the study screen (${theme})`, async ({ learnerPage, learner }) => {
      test.setTimeout(300_000)

      await learnerPage.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" })
      const sessionId = await startSession(learnerPage, learner.deckId)
      await waitForSettled(learnerPage)

      for (const viewport of VIEWPORTS) {
        await learnerPage.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        })
        // Reloaded rather than resized, for the same mount-time reason as `capture`,
        // and safe here because the session resumes from the server: the runner is
        // built so a reload continues rather than restarts.
        await learnerPage.goto(`/study/${sessionId}`)
        await waitForSettled(learnerPage)

        // A control proves the question actually rendered. Without this the capture
        // can land on the preparing spinner and the set would show a loading state
        // labelled as the study screen.
        await expect(
          learnerPage
            .getByRole("button", { name: /^(submit|continue|got it|next round)$/i })
            .first(),
        ).toBeVisible({ timeout: 120_000 })

        await learnerPage.screenshot({
          path: path.join(OUTPUT_DIR, `study-${theme}-${viewport.name}.png`),
          fullPage: true,
        })
      }
    })
  })
}
