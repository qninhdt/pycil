import { MASTERY_BANDS, masteryBand } from "@/lib/design/mastery"
import { cn } from "@/lib/utils"

/**
 * Where the learner sits on the mastery ramp.
 *
 * This is deliberately **not** a distribution across the five stages. No endpoint
 * returns per-stage counts: `/me/stats` carries only `{total, learned, mastered,
 * avgMastery}`, the folder item list carries no mastery at all, and per-item mastery
 * exists only on a deck read. Summing deck reads client-side would double-count any
 * sense held in two decks, which is exactly why the API resolves its own sense sets
 * with `SELECT DISTINCT`.
 *
 * So this renders what the figures actually support: the average as a marked position
 * on the ramp, plus the one true count the server does supply. Drawing five segments
 * from an average would be an invented shape presented as measured data.
 *
 * A rainbow scale is forbidden on this ramp: five hues would imply five unrelated
 * categories, when this is one ordered dimension.
 */
export function MasteryDistribution({
  avgMastery,
  learned,
  mastered,
}: {
  avgMastery: number
  learned: number
  mastered: number
}) {
  const band = masteryBand(avgMastery)

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-muted-foreground">Mastery</h2>

      {learned === 0 ? (
        <p className="text-sm text-muted-foreground">
          Your position on the ramp appears once you have reviewed something. Nothing
          here is hidden; there is simply no history to place yet.
        </p>
      ) : (
        <>
          {/* The five bands as equal segments, because they are the scale itself and
              not a measurement. Only the reached ones are filled, so the graphic says
              "this far along" rather than implying a count per band. */}
          <ol aria-hidden className="flex items-center gap-1">
            {MASTERY_BANDS.map((step) => (
              <li
                key={step.stage}
                data-stage={step.stage <= band.stage ? String(step.stage) : undefined}
                className={cn(
                  "h-2 flex-1 rounded-xs",
                  step.stage <= band.stage ? "stage-fill" : "bg-border",
                )}
              />
            ))}
          </ol>

          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            {/* The text carries the whole meaning, so the bar above can be hidden from
                the accessibility tree instead of being announced as five list items. */}
            <p className="text-sm">
              <span data-stage={String(band.stage)} className="stage-text font-medium">
                {band.name}
              </span>{" "}
              <span className="text-muted-foreground">
                on average, across {learned} reviewed{" "}
                {learned === 1 ? "word" : "words"}
              </span>
            </p>
            <p className="text-sm text-muted-foreground tabular-nums">
              {mastered} at {MASTERY_BANDS[MASTERY_BANDS.length - 1].name}
            </p>
          </div>
        </>
      )}
    </section>
  )
}
