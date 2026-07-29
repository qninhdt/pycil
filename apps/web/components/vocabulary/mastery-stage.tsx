import { MASTERY_STAGE_COUNT, masteryBand } from "@/lib/design/mastery"
import { cn } from "@/lib/utils"

/**
 * The five-pip mastery ramp.
 *
 * The stage index and its name arrive from the server on every read that carries
 * learning state (`masteryStage` and `masteryStageName` on a deck item), and the
 * band thresholds live in the API's learning policy. This component therefore maps
 * an index to a colour and nothing else: it must not decide what "mastered" means,
 * or the same score would be named one thing here and another in the API's own
 * statistics.
 *
 * When a response carries `mastery` but no stage — the search path does, since it
 * has no user scope — the local band table supplies both the index and the name
 * together, so the pip count and the label cannot disagree.
 */
export function MasteryStage({
  stage,
  mastery,
  stageName,
  className,
}: {
  /** 1-5, server-supplied. */
  stage?: number | null
  /** The raw score, used for the accessible label and as the stage fallback. */
  mastery?: number | null
  stageName?: string | null
  className?: string
}) {
  if (stage == null && mastery == null) return null

  const fallback = masteryBand(mastery ?? 0)
  const resolvedStage = stage ?? fallback.stage
  const name = stageName ?? fallback.name

  return (
    <span className={cn("flex items-center gap-2", className)}>
      <span
        className="flex items-center gap-0.5"
        role="img"
        aria-label={`${name}, stage ${resolvedStage} of ${MASTERY_STAGE_COUNT}`}
      >
        {Array.from({ length: MASTERY_STAGE_COUNT }, (_, index) => (
          <span
            key={index}
            aria-hidden
            data-stage={resolvedStage}
            className={cn(
              "h-1.5 w-3 rounded-xs",
              index < resolvedStage ? "stage-fill" : "bg-border",
            )}
          />
        ))}
      </span>
      <span className="text-xs text-muted-foreground">{name}</span>
    </span>
  )
}
