/**
 * The review-history window, resolved before any request is built.
 *
 * The API validates the window itself and answers `history_window_invalid` for an
 * inverted range or one wider than 365 days. This module exists so that error is
 * unreachable from the UI: a preset is chosen from a fixed set, and a hand-edited
 * query parameter is clamped here rather than forwarded and rejected.
 *
 * Day buckets are the only bucket the API supports, so no bucket choice is offered.
 */

/** The presets, all inside the API's own limits. */
export const HISTORY_PRESETS = [7, 30, 90, 365] as const

export type HistoryPreset = (typeof HISTORY_PRESETS)[number]

/** What the selector defaults to, matching the API's own default window. */
export const DEFAULT_HISTORY_DAYS: HistoryPreset = 30

function isPreset(value: number): value is HistoryPreset {
  return (HISTORY_PRESETS as readonly number[]).includes(value)
}

/**
 * Reads the day count out of a query parameter.
 *
 * Anything that is not one of the presets falls back to the default rather than being
 * clamped to a nearby number: a hand-edited value is a malformed request, and honouring
 * it approximately would render a chart whose axis does not match what was asked for.
 */
export function parseHistoryDays(value: string | undefined): HistoryPreset {
  if (!value) return DEFAULT_HISTORY_DAYS
  const parsed = Number(value)
  return Number.isInteger(parsed) && isPreset(parsed) ? parsed : DEFAULT_HISTORY_DAYS
}

/**
 * The `from` and `to` dates for a day count, as the API's `YYYY-MM-DD` strings.
 *
 * Inclusive of both ends, so seven days is seven buckets. `asOf` is passed in rather
 * than read here because the caller is a server component and the clock reading has to
 * happen in one place for the request and its label to agree.
 */
export function historyWindow(
  days: HistoryPreset,
  asOf: Date,
): { from: string; to: string } {
  const to = new Date(asOf)
  const from = new Date(asOf)
  from.setUTCDate(from.getUTCDate() - (days - 1))

  return { from: isoDate(from), to: isoDate(to) }
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}
