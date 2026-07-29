import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { HourglassIcon } from "@/lib/icons"
import { MAX_POLL_ATTEMPTS } from "@/lib/study/backoff"

/**
 * The three surfaces for a session that is waiting on the server.
 *
 * `preparing` and `waiting` are the only two states that ask the client to call
 * again, and `stalled` is where both land once the attempt budget is spent. They
 * share one frame because they differ only in wording: the shape of "we are waiting,
 * here is how long, here is your way out" is the same in all three, and three
 * near-identical files would drift apart on the next copy edit.
 *
 * The attempt count is visible on purpose. A spinner with no progress signal is
 * indistinguishable from a hang, and this wait can legitimately run for several
 * seconds while questions are generated upstream.
 */
function WaitingFrame({
  title,
  detail,
  attempt,
  children,
}: {
  title: string
  detail: string
  /** 1-based; omitted once polling has stopped. */
  attempt?: number
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-5 text-center">
      <div className="flex flex-col items-center gap-3">
        {attempt === undefined ? (
          <HourglassIcon className="size-5 text-muted-foreground" aria-hidden />
        ) : (
          <Spinner className="size-5 text-muted-foreground" />
        )}
        {/* Polite rather than assertive: this updates repeatedly while the learner
            waits, and an assertive region would interrupt a screen reader on every
            attempt. */}
        <h1 aria-live="polite" className="text-lg tracking-tight">
          {title}
        </h1>
      </div>

      <p className="max-w-sm text-sm text-muted-foreground">{detail}</p>

      {attempt !== undefined ? (
        <p className="font-mono text-xs text-muted-foreground tabular-nums">
          Attempt {attempt} of {MAX_POLL_ATTEMPTS}
        </p>
      ) : null}

      {children}
    </div>
  )
}

/** Supply is warming: eligible work exists but no question is ready yet. */
export function PreparingPanel({ attempt }: { attempt: number }) {
  return (
    <WaitingFrame
      title="Writing your next question"
      detail="Questions for this word are being generated. This usually takes a few seconds."
      attempt={attempt}
    />
  )
}

/**
 * Every remaining item is terminal but a grade has not settled.
 *
 * Distinct from `preparing` because the cause is different and so is the learner's
 * expectation: nothing more will be asked, the session is waiting on marking it has
 * already received.
 */
export function SettlingPanel({ attempt }: { attempt: number }) {
  return (
    <WaitingFrame
      title="Marking your last answer"
      detail="One answer is still being graded. The session finishes as soon as it lands."
      attempt={attempt}
    />
  )
}

/**
 * Polling gave up, or the server said it is out of preparation attempts.
 *
 * Not an error state. The work exists and may still arrive, so the only thing lost
 * is the automatic retry — hence a button rather than a dead end. Leaving is offered
 * beside it, because a learner who has waited this long may simply be done.
 */
export function StalledPanel({
  message,
  onRetry,
  onLeave,
  retrying,
}: {
  message: string
  onRetry: () => void
  onLeave: () => void
  retrying: boolean
}) {
  return (
    <WaitingFrame title="Still waiting on the server" detail={message}>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button onClick={onRetry} disabled={retrying}>
          Keep waiting
        </Button>
        <Button onClick={onLeave} variant="outline" disabled={retrying}>
          End session
        </Button>
      </div>
    </WaitingFrame>
  )
}
