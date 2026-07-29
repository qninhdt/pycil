import { cn } from "@/lib/utils"

/**
 * Where the learner is inside the current round.
 *
 * Discrete pips, not a percentage bar. A session has no knowable length: rounds
 * are variable waves, a sense can earn retries, and supply can defer a candidate
 * to a later round. A progress bar would therefore have to invent a denominator
 * and then walk backwards when the invention was wrong. Counting the current
 * round is the only honest measure available.
 *
 * The cap is server-supplied (`maxPerRound` on the session read). It is not
 * recomputed from deck settings here, because the session was planned once with
 * the settings that existed then and a later edit must not redraw this.
 */
export function RoundIndicator({
  roundIndex,
  served,
  maxPerRound,
  className,
}: {
  /** 0-based, as the server counts. Displayed 1-based. */
  roundIndex: number
  /** Questions delivered so far in this round. */
  served: number
  /** Null while the cap is unknown, in which case only the round number shows. */
  maxPerRound: number | null
  className?: string
}) {
  const cap = maxPerRound && maxPerRound > 0 ? maxPerRound : null

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className="text-xs tracking-wide text-muted-foreground uppercase">
        Round {roundIndex + 1}
      </span>

      {cap ? (
        <span
          className="flex items-center gap-1"
          role="img"
          aria-label={`${served} of up to ${cap} in this round`}
        >
          {Array.from({ length: cap }, (_, index) => (
            <span
              key={index}
              aria-hidden
              className={cn(
                "h-1 w-4 rounded-xs transition-colors",
                index < served ? "bg-primary" : "bg-border",
              )}
            />
          ))}
        </span>
      ) : null}
    </div>
  )
}
