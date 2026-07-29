import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { HourglassIcon, WarningIcon, WifiSlashIcon } from "@/lib/icons"

/**
 * A free-text answer being marked.
 *
 * Rule-graded formats settle in the same request. A rubric-graded one does not: the
 * server returns a task id and the verdict arrives over a realtime snapshot. So this
 * is a real waiting state, not a spinner over an answer that already exists.
 *
 * It cannot get permanently stuck. The task id is persisted, the subscribe proxy
 * replays the latest snapshot to whoever subscribes, and the server's reconciler
 * transitions the task even if the original enqueue was dropped. A reload, a dropped
 * socket and a lost worker message all converge on the same verdict.
 *
 * `stale` is therefore reserved for one thing: a re-subscribe that was **denied**.
 * A mere disconnect is not staleness, and showing a reconnect prompt for one would
 * teach the learner to distrust a screen that was about to settle on its own.
 */
export function PendingGradePanel({
  stale,
  failed,
  onReconnect,
}: {
  stale: boolean
  /**
   * The grading task reached a terminal failure or expired. Distinct from `stale`:
   * nothing is coming, so a reconnect would not help and is not offered.
   */
  failed: boolean
  onReconnect: () => void
}) {
  // Checked before `stale`, because a task that already failed is not waiting on a
  // subscription and offering to reconnect would send the learner after a result
  // that no longer exists.
  if (failed) {
    return (
      <div className="flex flex-col gap-2 border-t border-border pt-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-wash-warn px-2.5 py-1 text-xs font-medium tracking-wide text-on-wash-warn uppercase">
            <WarningIcon aria-hidden />
            Not marked
          </span>
        </div>
        {/* What happened to the learner's work is the thing worth stating: the answer
            was recorded, the mark was not, and moving on costs nothing. */}
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          This answer could not be marked. It stays on your record as answered, and
          you can carry on with the session.
        </p>
      </div>
    )
  }

  if (stale) {
    return (
      <div className="flex flex-col gap-3 border-t border-border pt-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-wash-warn px-2.5 py-1 text-xs font-medium tracking-wide text-on-wash-warn uppercase">
            <WifiSlashIcon aria-hidden />
            Not receiving updates
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          Your answer was sent and is being marked. This screen lost permission to
          receive the result, so it needs to reconnect to show it.
        </p>
        <Button onClick={onReconnect} variant="outline" size="sm" className="self-start">
          Reconnect
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-4">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-wash-warn px-2.5 py-1 text-xs font-medium tracking-wide text-on-wash-warn uppercase">
          <HourglassIcon aria-hidden />
          Marking
        </span>
        <Spinner className="text-muted-foreground" />
      </div>
      {/* Announced, because the learner has just submitted and is waiting on
          exactly this. */}
      <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
        Your answer is being marked. You can wait here; the result appears on its own.
      </p>
    </div>
  )
}
