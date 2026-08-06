import type { ForecastDay } from "@/lib/api/types"

/**
 * Two-letter weekday labels, indexed by `Date.getUTCDay()`.
 *
 * Hardcoded rather than derived from `toLocaleDateString`. This component
 * renders on the server, where the locale is the container's ICU default, and
 * hydrates in a browser using the visitor's. Those disagree for anyone not on
 * en-US: the server ships "Mo", the client expects "Lu", and React replaces the
 * text after hydration — a visible flash, and a mismatch the existing hydration
 * test cannot catch because CI runs both sides in the same locale.
 *
 * The rest of the interface is not translated, so a localised weekday would be
 * the only translated string on the page. When that changes, this should move
 * behind the same i18n mechanism as everything else rather than back to reading
 * the ambient locale.
 */
const WEEKDAY_INITIALS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"] as const

/** Weekday initials for a `YYYY-MM-DD` date. Identical on server and client. */
function weekday(date: string): string {
  // Parsed as UTC noon rather than midnight: a midnight UTC date shifts to the
  // previous day for anyone west of UTC, so every label would be off by one.
  const parsed = new Date(`${date}T12:00:00Z`)
  return WEEKDAY_INITIALS[parsed.getUTCDay()] ?? ""
}

/**
 * Seven days of upcoming review load, as bars.
 *
 * Heights are a share of the busiest day, not of a fixed ceiling: the useful
 * question is "which day is heavy", and a fixed scale flattens a quiet week into
 * seven invisible stubs. The counts are in the markup either way, so the bars
 * are decoration over a readable table rather than the only source.
 */
export function ForecastStrip({ forecast }: { forecast: ForecastDay[] }) {
  if (forecast.length === 0) return null

  const busiest = Math.max(...forecast.map((day) => day.dueCount))

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-muted-foreground">
        Next seven days
      </h2>

      <ol className="flex items-end gap-2">
        {forecast.map((day, index) => {
          const share = busiest === 0 ? 0 : day.dueCount / busiest
          return (
            <li key={day.date} className="flex flex-1 flex-col items-center gap-1.5">
              <span className="text-xs tabular-nums text-muted-foreground">
                {day.dueCount}
              </span>
              <span
                aria-hidden
                data-stage={day.dueCount === 0 ? undefined : "3"}
                className="w-full rounded-sm bg-muted stage-fill"
                // A 2px floor keeps an empty day visible as a baseline rather
                // than a gap in the row.
                style={{ height: `${Math.max(2, Math.round(share * 48))}px` }}
              />
              <span className={index === 0 ? "text-xs font-medium" : "text-xs text-muted-foreground"}>
                {index === 0 ? "Today" : weekday(day.date)}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
