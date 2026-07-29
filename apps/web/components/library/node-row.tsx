import Link from "next/link"

import { Badge } from "@/components/ui/badge"
import type { NodeRead } from "@/lib/api/types"
import { GlobeIcon } from "@/lib/icons"

import { NodeIcon, nodeTypeLabel } from "./node-icon"

/**
 * One row in a library listing.
 *
 * The count comes from the list response itself, so a listing of fifty decks costs
 * one request rather than fifty. `itemCount` is absent rather than zero where the
 * API did not compute it — a folder, or a reference — so an absent value renders
 * nothing instead of claiming the deck is empty.
 *
 * Due load is deliberately not here. Per-node due counts were cut from the list
 * response because they cannot be aggregated in bounded time; the opened node shows
 * its own.
 */
export function NodeRow({ node }: { node: NodeRead }) {
  const isDeck = node.type === "DECK"

  return (
    <li>
      <Link
        href={`/library/${node.id}`}
        className="group flex min-h-14 items-center gap-3 py-3 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <span className="shrink-0 text-muted-foreground">
          <NodeIcon type={node.type} />
        </span>

        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex items-center gap-2">
            <span className="truncate font-medium group-hover:underline">
              {node.name}
            </span>
            {node.visibility === "PUBLIC" ? (
              <span
                className="shrink-0 text-muted-foreground"
                title="Public"
              >
                <GlobeIcon />
                <span className="sr-only">Public</span>
              </span>
            ) : null}
          </span>

          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{nodeTypeLabel(node.type)}</span>
            {isDeck && node.itemCount != null ? (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums">
                  {node.itemCount} {node.itemCount === 1 ? "word" : "words"}
                </span>
              </>
            ) : null}
          </span>
        </span>

        {node.type === "REFERENCE" ? (
          <Badge variant="outline" className="shrink-0">
            Link
          </Badge>
        ) : null}
      </Link>
    </li>
  )
}
