import { Button } from "@/components/ui/button"
import { ArrowRightIcon, CoffeeIcon } from "@/lib/icons"

/**
 * The end of a round.
 *
 * A full screen rather than a toast, because a round boundary is a real unit of the
 * session and not an incidental notification. The server decides when a round closes
 * (the cap is per deck settings, applied at planning time) and reports the round being
 * entered, so this screen names what just finished rather than counting locally.
 *
 * Continuing calls `/next` again. That call is a mutation, so a second tap must not
 * double-advance. The guard is the reducer's, not a prop: dispatching `advance` moves
 * the screen to its loading phase before any call starts, and that phase offers no
 * button to tap twice.
 */
export function RoundBreakPanel({
  /** 0-based index of the round being entered, as the server counts them. */
  roundIndex,
  answeredInRound,
  onContinue,
}: {
  roundIndex: number
  answeredInRound: number
  onContinue: () => void
}) {
  // The server's index is 0-based and names the round about to start, so the one
  // that just closed is the number before it, in human counting.
  const closedRound = roundIndex

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-muted">
        <CoffeeIcon className="size-5 text-muted-foreground" aria-hidden />
      </span>

      <div className="flex flex-col gap-2">
        <h1 className="text-2xl tracking-tight">Round {closedRound} done</h1>
        <p className="text-sm text-muted-foreground">
          {answeredInRound === 0
            ? "Take a breath before the next round."
            : `${answeredInRound} ${answeredInRound === 1 ? "question" : "questions"} in that round. Take a breath before the next one.`}
        </p>
      </div>

      <Button onClick={onContinue} size="lg">
        Next round
        <ArrowRightIcon data-icon="inline-end" />
      </Button>
    </div>
  )
}
