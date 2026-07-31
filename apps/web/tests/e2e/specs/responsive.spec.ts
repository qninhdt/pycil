import type { ConsoleMessage, Page } from "@playwright/test"

import { startSession, waitForSettled } from "../fixtures/study-runner"
import { expect, test } from "../fixtures/test"

/**
 * The layout at its extremes, and the hydration that produces it.
 *
 * 320px is the narrowest viewport the design system commits to, and it is the width
 * where a fixed rail, a long headword, or a table that forgot `min-w-0` turns into a
 * horizontal scrollbar. That defect is invisible at every width the other specs run
 * at — `chromium` and `webkit` sit at 1440, `mobile-safari` at 390 — so nothing in
 * the suite would catch it.
 *
 * The hydration half belongs here rather than in its own file because it is the same
 * question asked at the same widths: the shell picks between the rail and the tab bar
 * in CSS precisely so the server and the client agree at every breakpoint
 * (`nav-rail.tsx`, `bottom-tab-bar.tsx`). A JS breakpoint hook would render one tree
 * on the server and possibly the other on the client, and React would say so.
 */

/** 320 is the floor; 375 and 768 are the breakpoints either side of the shell's `lg`. */
const WIDTHS = [320, 375, 768, 1440] as const

/** Screens reachable without setting up a session. */
const ROUTES = [
  { path: "/", name: "Today" },
  { path: "/library", name: "Library" },
  { path: "/progress", name: "Progress" },
  { path: "/settings", name: "Settings" },
] as const

/**
 * Whether the document scrolls sideways.
 *
 * Measured on `documentElement` rather than by looking for an overflowing element:
 * what matters to a reader is whether the page moves, and an element wider than the
 * viewport inside a container that clips it is not a defect.
 */
async function scrollsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const doc = document.documentElement
    // A pixel of tolerance: sub-pixel layout rounding at fractional zoom can report
    // a 0.5px overflow that no reader can scroll to.
    return doc.scrollWidth - doc.clientWidth > 1
  })
}

/** The element that actually overflows, so a failure names something fixable. */
async function widestOffender(page: Page): Promise<string> {
  return page.evaluate(() => {
    const limit = document.documentElement.clientWidth
    const offenders = Array.from(document.querySelectorAll("body *"))
      .map((element) => ({ element, rect: element.getBoundingClientRect() }))
      .filter(({ rect }) => rect.right > limit + 1 && rect.width > 0)
      .sort((a, b) => b.rect.right - a.rect.right)
      .slice(0, 3)
      .map(({ element, rect }) => {
        const tag = element.tagName.toLowerCase()
        const cls = (element.getAttribute("class") ?? "").slice(0, 80)
        return `${tag}.${cls} (right: ${Math.round(rect.right)}px)`
      })
    return offenders.join("\n    ") || "(no single element overflows; check a container)"
  })
}

test.describe("narrow viewports", () => {
  for (const route of ROUTES) {
    test(`${route.name} does not scroll sideways at any width`, async ({ page }) => {
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 800 })
        await page.goto(route.path)
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

        expect(
          await scrollsHorizontally(page),
          `${route.path} scrolls horizontally at ${width}px. Widest elements:\n    ` +
            (await widestOffender(page)),
        ).toBe(false)
      }
    })
  }

  test("a deck view does not scroll sideways at 320px", async ({ page, fixture }) => {
    // The deck is the densest screen: a row carries a headword, a part of speech, a
    // CEFR badge and a remove control on one line, so it is where a missing `min-w-0`
    // shows up first.
    await page.setViewportSize({ width: 320, height: 800 })
    await page.goto(`/library/${fixture.deckId}`)
    await expect(page.getByRole("heading", { name: fixture.deckName })).toBeVisible()

    expect(
      await scrollsHorizontally(page),
      `the deck view scrolls horizontally at 320px. Widest elements:\n    ` +
        (await widestOffender(page)),
    ).toBe(false)
  })

  test("the study screen does not scroll sideways at 320px", async ({
    learnerPage,
    learner,
  }) => {
    test.setTimeout(300_000)

    // Started before the resize so the session opens normally, then narrowed: the
    // study screen is the one a learner stays on, and its footer controls are the
    // most likely thing to push past a narrow viewport.
    await startSession(learnerPage, learner.deckId)

    await learnerPage.setViewportSize({ width: 320, height: 800 })
    await waitForSettled(learnerPage)

    expect(
      await scrollsHorizontally(learnerPage),
      `the study screen scrolls horizontally at 320px. Widest elements:\n    ` +
        (await widestOffender(learnerPage)),
    ).toBe(false)
  })

  /**
   * Exactly one navigation, at every width.
   *
   * The rail is `lg:flex` and the tab bar `lg:hidden`, so the two are meant to be
   * mutually exclusive. Both showing wastes a third of a 320px screen; neither
   * showing strands the reader with no navigation at all, and a plain "is the rail
   * visible" assertion would miss that second case entirely.
   */
  test("shows exactly one navigation at every width", async ({ page }) => {
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 800 })
      await page.goto("/library")
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible()

      // Both carry `aria-label="Primary"` on purpose — they are one navigation with
      // two renderings, and a screen reader should hear the same name either way. So
      // this counts *visible* matches rather than locating them separately: `display:
      // none` keeps the hidden one out of the accessibility tree, which is exactly
      // the property being asserted.
      const shown = page.getByRole("navigation", { name: "Primary" })
      await expect(
        shown,
        `${width}px should show exactly one primary navigation`,
      ).toHaveCount(1)
    }
  })
})

/**
 * Hydration, read from the console.
 *
 * React reports a server/client markup mismatch as an error on the console and
 * nowhere else — the page still renders, so no locator can see it. Collecting
 * console errors is the only way to assert the absence of one.
 */
test.describe("hydration", () => {
  test("no hydration mismatch at any breakpoint", async ({ page }) => {
    const errors: string[] = []
    const onConsole = (message: ConsoleMessage) => {
      if (message.type() !== "error") return
      const text = message.text()
      if (/hydrat|did not match|server (?:HTML|rendered)/i.test(text)) {
        errors.push(text)
      }
    }
    page.on("console", onConsole)

    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 800 })
      for (const route of ROUTES) {
        await page.goto(route.path)
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
      }
    }

    page.off("console", onConsole)
    expect(errors, `hydration mismatches reported:\n${errors.join("\n")}`).toEqual([])
  })
})
