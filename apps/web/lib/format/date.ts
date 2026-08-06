/**
 * Date display, formatted the same way on the server and in the browser.
 *
 * Every date on screen is rendered twice: once on the server, where the locale is
 * whatever ICU default the container happens to carry, and once during hydration,
 * where it is the visitor's. `toLocaleDateString(undefined, …)` reads the ambient
 * locale on both sides, so for anyone not on the server's locale the two disagree —
 * the markup says "3 Mar", the client renders "3 mars", and React replaces the text
 * after hydration. That is a visible flash on every such date, and CI cannot catch
 * it because both sides of a test run share one locale.
 *
 * So the locale is fixed here rather than inherited. The rest of the interface is
 * not translated; a localised date would be the only translated string on the page.
 * When the app gains i18n, this module is the one place that has to learn about it,
 * and it should take the locale from that mechanism rather than from the ambient
 * environment — which is the thing that was wrong to begin with.
 */

/**
 * The one locale every date is formatted in.
 *
 * Named rather than inlined so the i18n change is a single edit, and so a reader
 * can see that the choice is deliberate rather than a forgotten default.
 */
const DISPLAY_LOCALE = "en-GB"

/**
 * A `YYYY-MM-DD` string or an ISO timestamp, as a `Date` safe to format.
 *
 * A bare `YYYY-MM-DD` parses as midnight UTC, which is the previous day for anyone
 * west of UTC — so every such label would be off by one. Anchoring at UTC noon puts
 * the instant far enough from both boundaries that no real timezone crosses it.
 */
function anchor(value: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T12:00:00Z`)
    : new Date(value)
}

/**
 * "3 Mar" — a day within the current year, where the year is understood.
 *
 * Formatted in UTC as well as in a fixed locale. A timestamp near midnight would
 * otherwise name different days for two visitors reading the same screen, and the
 * server's rendering would agree with neither.
 */
export function shortDate(value: string | Date): string {
  const date = typeof value === "string" ? anchor(value) : value
  if (Number.isNaN(date.getTime())) return ""
  return new Intl.DateTimeFormat(DISPLAY_LOCALE, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date)
}
