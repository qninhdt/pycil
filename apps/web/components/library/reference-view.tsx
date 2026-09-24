import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import type { NodeRead, SenseContent } from "@/lib/api/types"
import { ArrowRightIcon, WarningIcon } from "@/lib/icons"

import { DeckItemList } from "./deck-item-list"
import { NodeHeader } from "./node-header"

/**
 * A reference: a pointer to a deck or folder that lives elsewhere in the tree.
 *
 * Two states, and they must not be conflated. When the target is readable, this
 * shows the target's words and links to it. When it is not — the owner made it
 * private again, or deleted it — the reference still exists in this tree and has
 * to say so, rather than rendering as a deck with no words in it.
 *
 * A revoked target is not an error either. Nothing here is broken: someone else
 * changed their mind about sharing. So it reads as a state, not a failure.
 */
export function ReferenceView({
  node,
  target,
  items,
  asOf,
  canEdit,
}: {
  node: NodeRead
  /** Null when the target is no longer readable by this viewer. */
  target: NodeRead | null
  /** The target's words, resolved from its whole readable subtree. */
  items: SenseContent[]
  /** The moment "due now" is judged against, read once on the server. */
  asOf: number
  canEdit: boolean
}) {
  const isFolder = target?.type === "FOLDER"
  return (
    <div className="flex flex-col gap-6">
      <NodeHeader node={node} canEdit={canEdit}>
        {target ? (
          <Button variant="outline" size="sm" render={<Link href={`/library/${target.id}`} />}>
            Open {isFolder ? "the folder" : "the deck"}
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        ) : null}
      </NodeHeader>

      {target ? (
        <>
          <p className="text-sm text-muted-foreground">
            This is a link to {target.name}. The words below are gathered from{" "}
            {isFolder ? "that folder and everything readable inside it" : "that deck"}, and
            changes made there appear here.
          </p>
          {/* Removal is disabled through a reference even for the owner of this
              node: the words belong to the target, and the person who can edit
              them is whoever owns it. */}
          <DeckItemList
            nodeId={target.id}
            ancestorIds={(target.path ?? []).map((step) => step.id)}
            items={items}
            asOf={asOf}
            canEdit={false}
          />
        </>
      ) : (
        <Alert>
          <WarningIcon />
          <AlertTitle>The linked item is no longer available</AlertTitle>
          <AlertDescription>
            Whoever owns it stopped sharing it, or removed it. This link stays in your
            library until you delete it, and will work again if the item is shared
            again.
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}
