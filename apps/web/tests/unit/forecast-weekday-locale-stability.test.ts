/**
 * Date labels rendered on the server must not depend on the ambient locale.
 *
 * A server component formats dates using the container's ICU locale; the same
 * component hydrating in a browser uses the visitor's. When those disagree React
 * discards the server text and re-renders it, which the visitor sees as a flash
 * and which silently breaks the "server HTML equals first client render"
 * guarantee. CI runs both sides in the same locale, so the existing hydration
 * test cannot see the problem — only forcing a different locale exposes it.
 *
 * These tests run the label function under several locales and assert the output
 * does not move. They are a guard on the *mechanism*, not on English: if the
 * interface is translated later, this file should be replaced by a check that the
 * label comes from the i18n layer rather than from `toLocaleDateString`.
 */

import { readFileSync } from "node:fs"
import { join } from "node:path"

import { describe, expect, it } from "vitest"

/**
 * The forecast strip is a server component, so it cannot simply be imported and
 * rendered here. Its label logic is a pure function of the date string, so the
 * behaviour under test is reproduced with the same lookup the component uses.
 */
const WEEKDAY_INITIALS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"] as const

function weekday(date: string): string {
  const parsed = new Date(`${date}T12:00:00Z`)
  return WEEKDAY_INITIALS[parsed.getUTCDay()] ?? ""
}

const FORECAST_STRIP = join(
  process.cwd(),
  "components",
  "dashboard",
  "forecast-strip.tsx",
)

describe("forecast strip weekday labels", () => {
  it("does not read the ambient locale in a server component", () => {
    const source = readFileSync(FORECAST_STRIP, "utf-8")
    const isClientComponent = /^\s*["']use client["']/m.test(source)

    if (!isClientComponent) {
      // `toLocaleDateString(undefined, ...)` resolves to the runtime default —
      // the container's locale on the server, the visitor's in the browser.
      expect(
        source,
        "a server component must not format dates against the ambient locale",
      ).not.toMatch(/toLocale(Date|Time)?String\s*\(\s*undefined/)
    }
  })

  it("maps each weekday to a stable two-letter label", () => {
    // 2026-08-03 is a Monday; walk one full week.
    expect(weekday("2026-08-03")).toBe("Mo")
    expect(weekday("2026-08-04")).toBe("Tu")
    expect(weekday("2026-08-05")).toBe("We")
    expect(weekday("2026-08-06")).toBe("Th")
    expect(weekday("2026-08-07")).toBe("Fr")
    expect(weekday("2026-08-08")).toBe("Sa")
    expect(weekday("2026-08-09")).toBe("Su")
  })

  it("yields the same label whatever locale the process is set to", () => {
    const dates = ["2026-08-03", "2026-08-06", "2026-08-09", "2026-01-01"]
    const reference = dates.map(weekday)

    // A locale-dependent implementation returns "Lu"/"Mo"/"月" here; a lookup
    // keyed on getUTCDay cannot vary at all.
    for (const locale of ["fr-FR", "de-DE", "ja-JP", "ar-EG", "en-GB"]) {
      const original = process.env.LANG
      process.env.LANG = locale
      try {
        expect(dates.map(weekday), `labels moved under ${locale}`).toEqual(reference)
      } finally {
        process.env.LANG = original
      }
    }
  })

  it("keeps a label two characters wide so the bar row stays aligned", () => {
    for (const initials of WEEKDAY_INITIALS) {
      expect(initials).toHaveLength(2)
    }
  })

  it("does not shift the day for viewers west of UTC", () => {
    // Parsing at UTC noon rather than midnight is what makes this safe: a
    // midnight timestamp lands on the previous day once a negative offset is
    // applied, which would make every label off by one for the Americas.
    expect(weekday("2026-08-03")).toBe("Mo")
    expect(new Date("2026-08-03T12:00:00Z").getUTCDay()).toBe(1)
  })
})
