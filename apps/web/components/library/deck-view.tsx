import Link from "next/link"

import { Button } from "@/components/ui/button"
import type { NodeRead, SenseContent } from "@/lib/api/types"
import { PlayIcon } from "@/lib/icons"

import { AddWordAction } from "./add-word-action"
import { DeckItemList } from "./deck-item-list"
import { NodeHeader } from "./node-header"

/**
 * A deck: its words, and the way into a session on them.
 *
 * Starting a session is a link to the launch screen rather than an action here.
 * The session-creating POST belongs to that screen, so a deck page reload cannot
 * start a second session as a side effect of rendering.
 */
export function DeckView({
  node,
  items,
  asOf,
  canEdit,
}: {
  node: NodeRead
  items: SenseContent[]
  /**
   * The moment "due now" is judged against, read once on the server and passed
   * down so the item rows render the same label on both passes.
   */
  asOf: number
  canEdit: boolean
}) {
  const ancestorIds = (node.path ?? []).map((ancestor) => ancestor.id)
  const count = node.itemCount ?? items.length

  return (
    <div className="flex flex-col gap-6">
      <NodeHeader node={node} canEdit={canEdit}>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {count} {count === 1 ? "word" : "words"}
          </span>

          {items.length > 0 ? (
            <Button render={<Link href={`/study/start/${node.id}`} />} size="sm">
              <PlayIcon data-icon="inline-start" />
              Study
            </Button>
          ) : null}

          {canEdit ? <AddWordAction nodeId={node.id} /> : null}
        </div>
      </NodeHeader>

      <DeckItemList
        nodeId={node.id}
        ancestorIds={ancestorIds}
        items={items}
        asOf={asOf}
        canEdit={canEdit}
      />
    </div>
  )
}
