import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import type { WeakSenseRead } from "@/lib/api/types"
import { masteryStageAttr, masteryStageName } from "@/lib/design/mastery"

/**
 * The handful of words with the lowest mastery, as a way into the sense detail
 * for each one.
 *
 * Every content field on a row is nullable: the API keeps a row whose sense was
 * regenerated away upstream, because the learner's own stats for it are still
 * real. Such a row still links somewhere useful, so it renders with the score and
 * a plain note instead of being dropped.
 */
export function WeakestPreview({ weakest }: { weakest: WeakSenseRead[] }) {
  if (weakest.length === 0) return null

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-muted-foreground">
        Needs the most work
      </h2>

      <ul className="flex flex-col divide-y divide-border border-y border-border">
        {weakest.map((sense) => (
          <li key={sense.senseId}>
            <Link
              href={`/w/${sense.senseId}`}
              className="flex min-h-11 items-center gap-3 py-2.5 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <span
                aria-hidden
                data-stage={masteryStageAttr(sense.mastery)}
                className="size-2 shrink-0 rounded-full stage-fill"
              />

              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-2">
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

              <span className="shrink-0 text-xs text-muted-foreground">
                {masteryStageName(sense.mastery)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
