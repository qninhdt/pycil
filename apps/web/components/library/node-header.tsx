import { Badge } from "@/components/ui/badge"
import type { NodeRead } from "@/lib/api/types"
import { GlobeIcon, LockIcon } from "@/lib/icons"

import { NodeActionsMenu } from "./node-actions-menu"
import { nodeTypeLabel } from "./node-icon"

/**
 * The header every node view shares: name, kind, visibility, and the actions menu.
 *
 * The actions menu is absent rather than disabled when the reader cannot write.
 * A disabled menu tells an anonymous visitor that renaming exists and is denied
 * to them, which is noise; absence just says the page is for reading.
 */
export function NodeHeader({
  node,
  canEdit,
  children,
}: {
  node: NodeRead
  canEdit: boolean
  /** Counts, stats, or a start-session control, depending on the node kind. */
  children?: React.ReactNode
}) {
  const isPublic = node.visibility === "PUBLIC"

  return (
    <header className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-xs tracking-wide text-muted-foreground uppercase">
              {nodeTypeLabel(node.type)}
            </span>
            <Badge variant="outline">
              {isPublic ? (
                <>
                  <GlobeIcon data-icon="inline-start" />
                  Shared by link
                </>
              ) : (
                <>
                  <LockIcon data-icon="inline-start" />
                  Private
                </>
              )}
            </Badge>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight">{node.name}</h1>

          {node.description ? (
            <p className="max-w-[65ch] text-sm text-muted-foreground">
              {node.description}
            </p>
          ) : null}
        </div>

        {canEdit ? <NodeActionsMenu node={node} /> : null}
      </div>

      {children}
    </header>
  )
}
