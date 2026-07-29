import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { MasteryStage } from "@/components/vocabulary/mastery-stage"
import type { WeakSense } from "@/lib/api/types"
import { TrendUpIcon } from "@/lib/icons"

/**
 * The words with the lowest mastery, as a way into each one.
 *
 * The full list rather than the dashboard's preview of five, and it carries the mastery
 * ramp per row so the ordering is visible rather than implied by position alone.
 *
 * Every content field is nullable on purpose. The API keeps a row whose sense was
 * regenerated away upstream, because the learner's own statistics for it are still
 * real, so a row can arrive with a score and no headword. Dropping those would quietly
 * shorten a list whose whole job is to be complete.
 */
export function WeakestWordList({ weakest }: { weakest: WeakSense[] }) {
  if (weakest.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <TrendUpIcon />
          </EmptyMedia>
          <EmptyTitle>Nothing to work on yet</EmptyTitle>
          <EmptyDescription>
            This list ranks words by how well you recall them, so it fills in once you
            have reviewed a few. Study a deck and come back.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <ul className="flex flex-col divide-y divide-border border-y border-border">
      {weakest.map((sense) => (
        <li key={sense.senseId}>
          <Link
            href={`/w/${sense.senseId}`}
            className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1.5 py-2.5 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-serif font-semibold">
                  {sense.word ?? "Untitled word"}
                </span>
                {sense.pos ? (
                  <span className="text-xs text-muted-foreground">{sense.pos}</span>
                ) : null}
                {sense.cefrLevel ? (
                  <Badge variant="outline">{sense.cefrLevel}</Badge>
                ) : null}
              </span>
              <span className="truncate font-serif text-xs text-muted-foreground">
                {sense.definition ?? "This word is no longer in the dictionary."}
              </span>
            </span>

            <MasteryStage mastery={sense.mastery} className="shrink-0" />
          </Link>
        </li>
      ))}
    </ul>
  )
}
