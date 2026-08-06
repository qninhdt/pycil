import Link from "next/link"

import { CefrChip } from "@/components/vocabulary/cefr-chip"
import { MasteryStage } from "@/components/vocabulary/mastery-stage"
import type { SenseContent } from "@/lib/api/types"
import { shortDate } from "@/lib/format/date"

/**
 * One sense in a deck.
 *
 * A row is renderable with a definition and nothing else. `word` is nullable because
 * the upstream dictionary can regenerate a sense away while the learner's own state
 * for it survives, and `senseId` is nullable for the same reason — so the row links
 * only when there is somewhere to link to.
 *
 * The learning block is absent rather than zeroed for a reader with no state on the
 * sense, which is what an anonymous visitor to a public deck sees.
 */
export function DeckItemRow({
  item,
  asOf,
  action,
}: {
  item: SenseContent
  /**
   * The moment "due now" is judged against, taken once on the server.
   *
   * Passed in rather than read here because this row renders on the client too, and
   * a clock read during render would let the server emit "Due now" while the client
   * emits a date — a hydration mismatch for a purely cosmetic label.
   */
  asOf: number
  /** The remove control, omitted for a reader who cannot write to this deck. */
  action?: React.ReactNode
}) {
  const body = (
    <span className="flex min-w-0 flex-1 flex-col gap-1">
      <span className="flex flex-wrap items-baseline gap-2">
        {item.word ? (
          <span className="font-serif font-semibold">{item.word}</span>
        ) : (
          <span className="text-sm text-muted-foreground">
            Word no longer available
          </span>
        )}
        {item.pos ? (
          <span className="text-xs text-muted-foreground">{item.pos}</span>
        ) : null}
        <CefrChip level={item.cefrLevel} />
      </span>

      <span className="font-serif text-sm text-muted-foreground">
        {item.definition}
      </span>

      {item.mastery != null ? (
        <span className="flex flex-wrap items-center gap-3">
          <MasteryStage
            stage={item.masteryStage}
            mastery={item.mastery}
            stageName={item.masteryStageName}
          />
          <ReviewSchedule nextReviewDate={item.nextReviewDate} asOf={asOf} />
        </span>
      ) : null}
    </span>
  )

  return (
    <li className="flex items-start gap-3 py-3">
      {item.senseId != null ? (
        <Link
          href={`/w/${item.senseId}`}
          className="flex min-w-0 flex-1 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {body}
        </Link>
      ) : (
        body
      )}
      {action}
    </li>
  )
}

/**
 * When this sense comes back.
 *
 * A date already past means it is due now, which is more useful to read than a date
 * the learner has to compare against today themselves.
 *
 * "Now" arrives as a prop rather than being read here. This component renders on the
 * client, so calling `Date.now()` during render would compare against a different
 * instant on the server than in the browser — a row on the boundary would hydrate
 * from "Due now" to a date, or the reverse. One reading taken by the caller keeps
 * both passes identical.
 */
function ReviewSchedule({
  nextReviewDate,
  asOf,
}: {
  nextReviewDate?: string | null
  asOf: number
}) {
  if (!nextReviewDate) return null

  const due = new Date(nextReviewDate)
  if (Number.isNaN(due.getTime())) return null

  if (due.getTime() <= asOf) {
    return <span className="text-xs text-muted-foreground">Due now</span>
  }

  return (
    <span className="font-mono text-xs text-muted-foreground">
      {shortDate(due)}
    </span>
  )
}
