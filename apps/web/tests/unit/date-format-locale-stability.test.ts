/**
 * Dates render identically whatever locale the reader's browser reports.
 *
 * The failure this pins is a hydration mismatch, and it is invisible to a normal
 * test run: the server and the client both execute in CI's locale, so they agree
 * and the bug shows only on a real visitor's machine. So the disagreement is
 * reproduced here directly — `ambient` is what `toLocaleDateString(undefined, …)`
 * returns on a machine set to each locale, which is precisely the call the two
 * fixed sites used to make.
 *
 * The load-bearing assertion is that `ambient` varies across these locales while
 * `shortDate` does not. If `ambient` ever stopped varying, this file would pass
 * without proving anything — so that is asserted too.
 */

import { describe, expect, it } from "vitest"

import { shortDate } from "@/lib/format/date"

/** Locales whose short-date rendering genuinely differs from one another. */
const LOCALES = ["en-US", "en-GB", "fr-FR", "de-DE", "ja-JP", "vi-VN"]

/** What the replaced call produced on a machine reporting `locale`. */
function ambient(value: string, locale: string): string {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString(locale, {
    month: "short",
    day: "numeric",
  })
}

describe("shortDate", () => {
  it("renders the fixed locale, not the machine's", () => {
    const byAmbient = new Set(LOCALES.map((locale) => ambient("2026-03-03", locale)))
    // Guards against a vacuous pass: if every locale agreed, the assertion below
    // would hold for a formatter that still read the ambient locale.
    expect(
      byAmbient.size,
      "these locales no longer disagree, so this test proves nothing — pick others",
    ).toBeGreaterThan(1)

    // Pinned to the literal rendering rather than to "it is stable", which a
    // formatter taking no locale argument satisfies trivially. Only a formatter that
    // *names* its locale produces this on a machine reporting some other one — which
    // is the property the hydration mismatch violated.
    expect(shortDate("2026-03-03")).toBe("3 Mar")
  })

  it("does not shift a bare date to the previous day west of UTC", () => {
    // The defect a naive `new Date("2026-03-03")` produces: midnight UTC is the 2nd
    // for anyone west of it, so every label reads one day early. Anchoring at noon
    // is what makes the 3rd stay the 3rd.
    expect(shortDate("2026-03-03")).toContain("3")
    expect(shortDate("2026-03-03")).not.toContain("2 ")
  })

  it("formats a bare date and its noon-UTC timestamp the same", () => {
    expect(shortDate("2026-03-03")).toBe(shortDate("2026-03-03T12:00:00Z"))
  })

  it("names the UTC day for a timestamp near midnight", () => {
    // Two readers either side of UTC read the same screen; the day named must be the
    // server's, not each machine's. 23:30Z on the 3rd is already the 4th in Tokyo.
    expect(shortDate("2026-03-03T23:30:00Z")).toBe(shortDate("2026-03-03"))
  })

  it("renders nothing for a value that is not a date", () => {
    // A malformed date must not put "Invalid Date" on screen next to a word.
    expect(shortDate("not-a-date")).toBe("")
  })
})
