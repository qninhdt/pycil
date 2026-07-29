import {
  Empty,
  EmptyDescription,
  EmptyTitle,
} from "@/components/ui/empty"
import type { NodeRead } from "@/lib/api/types"

import { NodeRow } from "./node-row"

/**
 * A listing of child nodes.
 *
 * The empty state is composed rather than a bare sentence, because an empty library
 * is the state a new account starts in: it is the first screen a learner sees, so it
 * has to say what to do next. The action is passed in rather than built here, since
 * only a signed-in owner may create anything.
 */
export function NodeList({
  nodes,
  emptyAction,
  emptyTitle = "Nothing here yet",
  emptyDescription = "Make a folder to organise your words, or a deck to start studying them.",
}: {
  nodes: NodeRead[]
  /** Rendered inside the empty state. Omitted for a reader who cannot create. */
  emptyAction?: React.ReactNode
  emptyTitle?: string
  emptyDescription?: string
}) {
  if (nodes.length === 0) {
    return (
      <Empty>
        <EmptyTitle>{emptyTitle}</EmptyTitle>
        <EmptyDescription>{emptyDescription}</EmptyDescription>
        {emptyAction ? <div className="mt-2">{emptyAction}</div> : null}
      </Empty>
    )
  }

  return (
    <ul className="flex flex-col divide-y divide-border border-y border-border">
      {nodes.map((node) => (
        <NodeRow key={node.id} node={node} />
      ))}
    </ul>
  )
}
