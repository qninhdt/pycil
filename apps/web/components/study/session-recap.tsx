import Link from "next/link"

import { Button } from "@/components/ui/button"
import type { SessionState } from "@/lib/api/types"
import { ArrowRightIcon, CheckCircleIcon } from "@/lib/icons"

/**
 * What the session came to.
 *
 * Read from `GET /v1/sessions/{id}` rather than accumulated on the client, because
 * reaching `exhausted` deletes the live Redis namespace and only a persisted summary
 * row is left behind. That is what makes this screen survive a reload: the counts
 * come from the row, so a refresh re-reads them instead of losing them with the tab's
 * memory.
 *
 * Figures only, and only ones the server actually sends. There is no accuracy
 * percentage here because a session with one pending grade would compute two
 * different rates a second apart.
 */
export function SessionRecap({
  session,
  /** Where "back to the deck" goes. Absent when the summary carries no node. */
  nodeId,
}: {
  session: SessionState
  nodeId: string | null
}) {
  const answered = session.answersTotal ?? 0
  const correct = session.answersCorrect ?? 0
  const completed = session.sensesCompleted ?? 0
  const admitted = session.sensesAdmitted ?? 0
  const rounds = session.roundsUsed ?? 0

  return (
    <div className="flex flex-col items-center gap-8 text-center">
      <div className="flex flex-col items-center gap-3">
        <CheckCircleIcon className="size-6 text-muted-foreground" aria-hidden />
        <h1 className="text-2xl tracking-tight">Session complete</h1>
        <p className="text-sm text-muted-foreground">
          {completed} of {admitted} {admitted === 1 ? "word" : "words"} finished
          {rounds > 0 ? ` across ${rounds} ${rounds === 1 ? "round" : "rounds"}` : ""}.
        </p>
      </div>

      <dl className="grid w-full grid-cols-2 gap-4">
        <Figure label="Answered" value={answered} />
        <Figure label="Correct" value={correct} />
      </dl>

      <div className="flex flex-wrap items-center justify-center gap-3">
        {nodeId ? (
          <>
            <Button render={<Link href={`/study/start/${nodeId}`} />}>
              Study again
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
            <Button render={<Link href={`/library/${nodeId}`} />} variant="outline">
              Back to the deck
            </Button>
          </>
        ) : (
          <Button render={<Link href="/library" />} variant="outline">
            Back to the library
          </Button>
        )}
      </div>
    </div>
  )
}

function Figure({
  label,
  value,
  hint,
}: {
  label: string
  value: number
  hint?: string
}) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-border px-4 py-3">
      <dt className="text-xs tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className="font-mono text-2xl tabular-nums">{value}</dd>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}
