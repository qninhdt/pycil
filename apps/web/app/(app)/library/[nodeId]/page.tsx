"use client"

import { use, useEffect, useState } from "react"

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
} from "@/lib/actions/library-reads"
import type { FolderStats, NodeRead, SenseContent } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

type Body =
  | { kind: "deck"; items: SenseContent[] }
  | { kind: "reference"; target: NodeRead | null; items: SenseContent[] }
  | { kind: "folder"; stats: FolderStats | null; children: NodeRead[] }

export default function NodePage({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = use(params)
  const [node, setNode] = useState<NodeRead | null | undefined>(undefined)
  const [body, setBody] = useState<Body | null>(null)
  const [canEdit, setCanEdit] = useState(false)
  const [asOf, setAsOf] = useState(0)

  useEffect(() => {
    let active = true
    void (async () => {
      const next = await readNode(nodeId)
      if (!active) return
      setNode(next)
      if (!next) return
      setAsOf(Date.now())
      setCanEdit(await canEditNode(nodeId))
      if (next.type === "DECK") {
        setBody({ kind: "deck", items: await readDeckItems(next.id) })
      } else if (next.type === "REFERENCE") {
        const target = next.targetNodeId ? await readNode(next.targetNodeId) : null
        // A reference may point at a folder as well as a deck. Reading a folder's
        // words through the deck endpoint is rejected by the API, so the target's
        // own type decides which read to make.
        const items = !target
          ? []
          : target.type === "DECK"
            ? await readDeckItems(target.id)
            : (await readFolderContents(target.id)).items
        setBody({ kind: "reference", target, items })
      } else {
        const contents = await readFolderContents(next.id)
        setBody({ kind: "folder", stats: contents.stats, children: contents.children.items })
      }
    })()
    return () => {
      active = false
    }
  }, [nodeId])

  if (node === undefined || (node && !body)) return <Spinner aria-label="Loading library item" />
  if (!node) return <p className="text-sm text-muted-foreground">This item is not available.</p>

  return (
    <div className="flex flex-col gap-6">
      <NodeBreadcrumb
        path={node.path ?? []}
        current={node.name}
        hasHiddenAncestors={Boolean(node.parentNodeId) && (node.path ?? []).length === 0}
      />
      {!canEdit ? <AnonymousReadNotice /> : null}
      {body?.kind === "deck" ? (
        <DeckView node={node} items={body.items} asOf={asOf} canEdit={canEdit} />
      ) : null}
      {body?.kind === "reference" ? (
        <ReferenceView
          node={node}
          target={body.target}
          items={body.items}
          asOf={asOf}
          canEdit={canEdit}
        />
      ) : null}
      {body?.kind === "folder" ? (
        <FolderView
          node={node}
          childNodes={body.children}
          stats={body.stats}
          canEdit={canEdit}
        />
      ) : null}
    </div>
  )
}
