import AxeBuilder from "@axe-core/playwright"
import type { Page } from "@playwright/test"

import { startSession, waitForSettled } from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * Accessibility, asserted in a real browser rather than in isolation.
 *
 * Storybook already runs `addon-a11y` over each component on its own, and that is the
 * cheaper place to catch a missing label on a button. What it cannot see is the
 * composed page: a heading order that only breaks once three sections are stacked, a
 * landmark duplicated by the shell, a focus trap that needs the real dialog and the
 * real router. So this file scans whole screens and drives them from the keyboard
 * alone.
 *
 * Violations are asserted as an empty list rather than a count under some threshold.
 * A threshold encodes today's defects as tomorrow's target and quietly permits the
 * next one.
 */

/**
 * The rule sets worth failing a build over.
 *
 * WCAG 2.1 A and AA, which is the standard the design system was specified against.
 * `best-practice` is deliberately excluded: it carries opinions (a page should have
 * one `main`, lists should not be nested a certain way) that are not conformance
 * requirements, and mixing them in makes a failure ambiguous about whether the
 * product is inaccessible or merely unfashionable.
 */
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

/** Scans the current page and returns the violations, most serious first. */
async function scan(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze()
  return violations
}

/**
 * A readable failure. Axe's own objects are large and nested, so dumping them raw
 * buries the one line that says what to fix.
 */
function describeViolations(violations: Awaited<ReturnType<typeof scan>>): string {
  return violations
    .map(
      (violation) =>
        `${violation.impact ?? "unknown"}: ${violation.id} — ${violation.help}\n` +
        violation.nodes
          .slice(0, 3)
          .map((node) => `    ${node.target.join(" ")}`)
          .join("\n"),
    )
    .join("\n")
}

test.describe("accessibility", () => {
  /**
   * Every signed-in screen, scanned as it actually renders.
   *
   * One test per route rather than a loop inside one test, so a failure names the
   * screen that failed instead of stopping the whole sweep at the first one.
   */
  const ROUTES = [
    { path: "/", name: "Today" },
    { path: "/library", name: "Library" },
    { path: "/progress", name: "Progress" },
    { path: "/settings", name: "Settings" },
  ]

  for (const route of ROUTES) {
    test(`${route.name} has no WCAG A or AA violations`, async ({ page }) => {
      await page.goto(route.path)

      // Scanned after the screen has settled. These routes are server-rendered with
      // client islands, and scanning mid-hydration reports on markup that is about to
      // be replaced — a false positive that would flake rather than inform.
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

      const violations = await scan(page)
      expect(
        violations,
        `${route.path} has accessibility violations:\n${describeViolations(violations)}`,
      ).toEqual([])
    })
  }

  test("a deck view has no violations", async ({ page, fixture }) => {
    await page.goto(`/library/${fixture.deckId}`)
    await expect(page.getByRole("heading", { name: fixture.deckName })).toBeVisible()

    const violations = await scan(page)
    expect(
      violations,
      `the deck view has accessibility violations:\n${describeViolations(violations)}`,
    ).toEqual([])
  })

  test("a sense page has no violations", async ({ page, fixture }) => {
    await page.goto(`/w/${fixture.publicSenseId}`)
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

    const violations = await scan(page)
    expect(
      violations,
      `the sense page has accessibility violations:\n${describeViolations(violations)}`,
    ).toEqual([])
  })

  test("the sign-in screen has no violations", async ({ anonymousPage }) => {
    await anonymousPage.goto("/login")
    await expect(anonymousPage.getByRole("heading", { level: 1 })).toBeVisible()

    const violations = await scan(anonymousPage)
    expect(
      violations,
      `the sign-in screen has accessibility violations:\n${describeViolations(violations)}`,
    ).toEqual([])
  })

  /**
   * The study screen, which is the one that matters most.
   *
   * It is the only screen a learner spends real time on, it is the most dynamic, and
   * it is the only one whose primary control changes identity as the session moves —
   * so it is also the easiest to leave unlabelled.
   */
  test("the study screen has no violations", async ({ learnerPage, learner }) => {
    test.setTimeout(300_000)
    await startSession(learnerPage, learner.deckId)

    const violations = await scan(learnerPage)
    expect(
      violations,
      `the study screen has accessibility violations:\n${describeViolations(violations)}`,
    ).toEqual([])
  })

  test("the command palette has no violations while open", async ({ page }) => {
    await page.goto("/library")
    await page.keyboard.press("ControlOrMeta+k")
    await expect(
      page.getByPlaceholder(/search words, or jump to a screen/i),
    ).toBeVisible()

    const violations = await scan(page)
    expect(
      violations,
      `the open palette has accessibility violations:\n${describeViolations(violations)}`,
    ).toEqual([])
  })
})

test.describe("keyboard-only operation", () => {
  /**
   * A study question answered without a pointer.
   *
   * The runner binds digits to choices and Enter to submit at the document rather
   * than on each control, specifically so Enter works while focus sits in the answer
   * input. This drives that path: no `click` anywhere in the test.
   */
  test("answers a study question using only the keyboard", async ({
    learnerPage,
    learner,
    fixture,
  }) => {
    test.skip(!fixture.supplyWarmed, "Needs a retrievable assessment to answer.")
    test.setTimeout(300_000)

    await startSession(learnerPage, learner.deckId)

    // Every session opens on an exposure card, whose only action is "Got it". Enter
    // advances it, which is the same binding a graded question and a round break use.
    const gotIt = learnerPage.getByRole("button", { name: /^got it$/i })
    if (await gotIt.isVisible().catch(() => false)) {
      await learnerPage.keyboard.press("Enter")
      await waitForSettled(learnerPage)
    }

    // A single-choice question is the format the digit shortcuts exist for. Skipped
    // rather than failed if the planner served something else: which format comes up
    // is the sampler's decision, and this test is about the keyboard, not the sampler.
    const radios = learnerPage.getByRole("radio")
    test.skip(
      (await radios.count()) === 0,
      "This round did not open on a single-choice question, which is what the " +
        "digit shortcuts apply to.",
    )

    // "1" selects the first option. Not a click, and not focus-then-space: the digit
    // binding is a distinct path and the only one a learner using a keyboard reaches.
    await learnerPage.keyboard.press("1")
    await expect(radios.first()).toBeChecked()

    // Enter submits. The runner refuses an empty answer, so reaching a verdict here
    // also proves the digit press registered as an answer rather than only visually.
    await learnerPage.keyboard.press("Enter")

    await expect(
      learnerPage.getByRole("button", { name: /^continue$/i }),
    ).toBeVisible({ timeout: 120_000 })
  })

  test("opens, searches and closes the palette using only the keyboard", async ({
    page,
    fixture,
  }) => {
    test.skip(fixture.seededWords.length === 0, "Needs a searchable seeded word.")

    await page.goto("/library")

    // Opened from the shortcut with nothing focused: the binding is on the window.
    await page.keyboard.press("ControlOrMeta+k")

    const input = page.getByPlaceholder(/search words, or jump to a screen/i)
    await expect(input).toBeVisible()

    // Focus must be *in* the input already. A palette that opens without focusing its
    // field forces a keyboard user to tab into it, which is the difference between a
    // shortcut and a decoration.
    await expect(input).toBeFocused()

    await page.keyboard.type("progress")

    // Arrow keys move the active option, and Enter takes it. cmdk marks the active
    // option with `aria-selected`, so this asserts on the accessible state rather than
    // on a class name.
    const goTo = page.getByRole("group", { name: "Go to" })
    const option = goTo.getByRole("option", { name: /progress/i }).first()
    await expect(option).toBeVisible({ timeout: 30_000 })

    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")

    await expect(page).toHaveURL(/\/progress/)
  })

  test("shows a visible focus ring on the primary control of every screen", async ({
    page,
  }) => {
    for (const path of ["/", "/library", "/progress", "/settings"]) {
      await page.goto(path)
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

      // Tab from the document, then read what the browser considers focused. The
      // assertion is that focus is *visible*, which is why it reads the computed
      // outline rather than merely checking that something is focused: a control that
      // takes focus with `outline: none` and no replacement is the exact defect this
      // is looking for.
      await page.keyboard.press("Tab")

      const focused = page.locator(":focus-visible")
      await expect(
        focused,
        `${path} moved focus nowhere on the first Tab`,
      ).toHaveCount(1)

      const ring = await focused.evaluate((element) => {
        const style = getComputedStyle(element)
        return {
          outlineWidth: style.outlineWidth,
          outlineStyle: style.outlineStyle,
          boxShadow: style.boxShadow,
        }
      })

      // The design system draws focus as a ring, which Tailwind implements as a box
      // shadow, and some primitives use a real outline. Either satisfies the
      // requirement; neither being present does not.
      const hasRing =
        (ring.outlineStyle !== "none" && ring.outlineWidth !== "0px") ||
        (ring.boxShadow !== "none" && ring.boxShadow !== "")
      expect(
        hasRing,
        `${path}: the first focusable control has no visible focus indicator ` +
          `(outline: ${ring.outlineStyle} ${ring.outlineWidth}, shadow: ${ring.boxShadow})`,
      ).toBe(true)
    }
  })
})

/**
 * The reduced-motion preference, set at the browser rather than mocked.
 *
 * `app/globals.css` collapses every animation and transition to 0.01ms under the
 * query, and `lib/design/motion.ts` expects Motion consumers to degrade through
 * `useReducedMotion`. Playwright can set the real media feature, so this asserts the
 * computed result rather than the presence of the rule.
 */
test.describe("reduced motion", () => {
  test("collapses transitions when the preference is set", async ({ page }) => {
    // Set per page rather than through `test.use({ reducedMotion })`. The
    // learner-scoped fixtures build their own `browser.newContext`, so a
    // project-level option would not reach them — the preference would silently be
    // unset on exactly the page the second test asserts against, and it would pass
    // while proving nothing.
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/library")
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

    // Read off a real element rather than a probe injected for the test: the global
    // rule uses `*`, so anything on the page is subject to it, and asserting on
    // something the app actually renders is what makes this meaningful.
    const durations = await page.evaluate(() => {
      const elements = Array.from(document.querySelectorAll("main *")).slice(0, 40)
      return elements.map((element) => getComputedStyle(element).transitionDuration)
    })

    // Every duration is either absent or collapsed. A single uncollapsed transition
    // means the rule was overridden by something more specific, which is precisely
    // the regression a `!important` global is meant to prevent.
    //
    // Parsed as a number rather than matched as a string. `transition-duration:
    // 0.01ms` is 1e-5 seconds, and the serialisation of that is the engine's
    // choice: Chromium reports `1e-05s`, so a string comparison against
    // `"0.00001s"` failed on 17 correctly-collapsed transitions and reported the
    // opposite of the truth. A millisecond is the threshold because anything at or
    // below it is imperceptible, which is what the preference actually asks for.
    const uncollapsed = durations.filter(
      (duration) => (Number.parseFloat(duration) || 0) > 0.001,
    )
    expect(
      uncollapsed,
      `transitions survived the reduced-motion preference: ${uncollapsed.join(", ")}`,
    ).toEqual([])
  })

  test("the study screen is still operable with motion off", async ({
    learnerPage,
    learner,
  }) => {
    test.setTimeout(300_000)

    // Set here explicitly: `learnerPage` comes from its own context, so it inherits
    // no project-level media option.
    await learnerPage.emulateMedia({ reducedMotion: "reduce" })

    // The runner reveals each question through the shared entry transition, so a
    // reduced-motion path that returned `initial: {opacity: 0}` and never animated
    // would leave the question invisible while every locator still resolved. Reaching
    // a settled control proves the screen is usable, not merely mounted.
    await startSession(learnerPage, learner.deckId)
    await waitForSettled(learnerPage)

    await expect(learnerPage.locator("main")).toBeVisible()
  })
})
