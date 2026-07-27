import type { FSRSForecastDay } from "@/lib/api/types"

/** Weekday initial for a `YYYY-MM-DD` date, in the viewer's locale. */
function weekday(date: string): string {
  // Parsed as UTC noon rather than midnight: a midnight UTC date shifts to the
  // previous day for anyone west of UTC, so every label would be off by one.
  const parsed = new Date(`${date}T12:00:00Z`)
  return parsed.toLocaleDateString(undefined, { weekday: "short" }).slice(0, 2)
}

/**
 * Seven days of upcoming review load, as bars.
 *
 * Heights are a share of the busiest day, not of a fixed ceiling: the useful
 * question is "which day is heavy", and a fixed scale flattens a quiet week into
 * seven invisible stubs. The counts are in the markup either way, so the bars
 * are decoration over a readable table rather than the only source.
 */
export function ForecastStrip({ forecast }: { forecast: FSRSForecastDay[] }) {
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
