import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import type { SenseRelation } from "@/lib/api/types"

/**
 * Related senses, grouped by relation type.
 *
 * A relation has three possible target states, and conflating them produces dead
 * links:
 *
 * - resolved to a specific sense (`toSenseId` present) — links to that sense
 * - a known word whose sense was never disambiguated (`toSenseId` null) — there is
 *   nothing sense-shaped to open, so the word is named without a link
 * - a word Lexi has not generated yet (`toWordStatus: "pending"`) — labelled as
 *   such, because linking to it would 404
 *
 * `wsdState` is what reports the disambiguation attempt, and it is the reason
 * `toSenseId` can be null on an otherwise valid relation. The state itself is
 * internal vocabulary, so the unresolved case is labelled in plain words instead: a
 * reader who sees a word with no link learns why without being handed a term from
 * the pipeline.
 */

/** Turns `near_synonym` into "Near synonym" without a hardcoded label table. */
function relationLabel(relType: string): string {
  const spaced = relType.replace(/_/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

function groupByType(relations: SenseRelation[]): [string, SenseRelation[]][] {
  const groups = new Map<string, SenseRelation[]>()
  for (const relation of relations) {
    const existing = groups.get(relation.relType)
    if (existing) {
      existing.push(relation)
      continue
    }
    groups.set(relation.relType, [relation])
  }
  return [...groups.entries()]
}

export function RelationList({ relations }: { relations: SenseRelation[] }) {
  if (relations.length === 0) return null

  return (
    <div className="flex flex-col gap-4">
      {groupByType(relations).map(([relType, group]) => (
        <div key={relType} className="flex flex-col gap-2">
          <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {relationLabel(relType)}
          </h3>
          <ul className="flex flex-col gap-1.5">
            {group.map((relation) => (
              <li key={`${relation.toWordId}-${relation.toSenseId ?? "unresolved"}`}>
                <RelationTarget relation={relation} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

function RelationTarget({ relation }: { relation: SenseRelation }) {
  const isPending = relation.toWordStatus === "pending"

  // Only a resolved sense has somewhere to go. The other two states render as
  // text, so a reader is never offered a link that cannot resolve.
  if (relation.toSenseId != null && !isPending) {
    return (
      <Link
        href={`/w/${relation.toSenseId}`}
        className="flex min-h-8 items-baseline gap-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <span className="font-medium">{relation.toWordDisplay}</span>
        {relation.toSenseGloss ? (
          <span className="truncate font-serif text-xs text-muted-foreground">
            {relation.toSenseGloss}
          </span>
        ) : null}
      </Link>
    )
  }

  return (
    <span className="flex min-h-8 items-baseline gap-2">
      <span className="font-medium text-muted-foreground">
        {relation.toWordDisplay}
      </span>
      <Badge variant="outline">
        {isPending ? "Not generated yet" : "Sense not identified"}
      </Badge>
    </span>
  )
}
