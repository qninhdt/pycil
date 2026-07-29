import { notFound } from "next/navigation"

import { AnonymousReadNotice } from "@/components/library/anonymous-read-notice"
import { DeckView } from "@/components/library/deck-view"
import { FolderView } from "@/components/library/folder-view"
import { NodeBreadcrumb } from "@/components/library/node-breadcrumb"
import { ReferenceView } from "@/components/library/reference-view"
import {
  canEditNode,
  readDeckItems,
  readFolderContents,
  readNode,
  readServerNow,
} from "@/lib/actions/library-reads"
import type { NodeRead } from "@/lib/api/types"
import { getSession } from "@/lib/auth/session"

/**
 * One node, three kinds.
 *
 * Folders, decks and references are one table with a `type` discriminator, so they
 * are one route with one read and a switch. Splitting them into three routes would
 * mean a caller has to know the kind before it can build a URL, which it does not
 * when following a link someone shared.
 */
export default async function NodePage({
  params,
}: {
  params: Promise<{ nodeId: string }>
}) {
  const { nodeId } = await params

  const node = await readNode(nodeId)
  // Unknown, private to someone else, and soft-deleted all arrive as one 404 from
  // the API on purpose, so this cannot and should not report which it was.
  if (!node) notFound()

  const session = await getSession()
  const canEdit = await canEditNode(nodeId)

  return (
    <div className="flex flex-col gap-6">
      {/* `path` is absent on a list read and present on this one, and it is
          truncated at the first ancestor the caller cannot see. An empty path with
          a parent set therefore means the trail was filtered, not that the node
          sits at the root — the page knows both facts, so it says which. */}
      <NodeBreadcrumb
        path={node.path ?? []}
        current={node.name}
        hasHiddenAncestors={
          Boolean(node.parentNodeId) && (node.path ?? []).length === 0
        }
      />

      {/* A signed-out reader arrived on someone else's shared link. Saying so once,
          at the top, is what makes the absence of every edit control legible rather
          than looking like a half-broken screen. */}
      {!session.isLoggedIn ? <AnonymousReadNotice /> : null}

      <NodeBody node={node} canEdit={canEdit} />
    </div>
  )
}

async function NodeBody({ node, canEdit }: { node: NodeRead; canEdit: boolean }) {
  // One clock reading for the whole render. It comes from the data module rather
  // than being read here: deck rows compare review dates against it to decide
  // "Due now" and they render on the client too, so a clock read inside a
  // component would let the two passes disagree and hydrate one label into the
  // other.
  const asOf = await readServerNow()

  if (node.type === "DECK") {
    const items = await readDeckItems(node.id)
    return <DeckView node={node} items={items} asOf={asOf} canEdit={canEdit} />
  }

  if (node.type === "REFERENCE") {
    // A reference points at a deck elsewhere in the tree, and inherited access to
    // that deck can be revoked after the reference was made. So the target is read
    // separately and allowed to be null, which is the revoked state the view shows.
    const target = node.targetNodeId ? await readNode(node.targetNodeId) : null
    const items = target ? await readDeckItems(target.id) : []
    return (
      <ReferenceView
        node={node}
        target={target}
        items={items}
        asOf={asOf}
        canEdit={canEdit}
      />
    )
  }

  const { stats, children } = await readFolderContents(node.id)
  return (
    <FolderView
      node={node}
      childNodes={children.items}
      stats={stats}
      canEdit={canEdit}
    />
  )
}
