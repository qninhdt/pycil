"use client"

import { useEffect, useState } from "react"

import { CreateNodeSheet } from "@/components/library/create-node-sheet"
import { NodeList } from "@/components/library/node-list"
import { readNodeChildren } from "@/lib/actions/library-reads"
import type { NodeRead } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

export default function LibraryPage() {
  const [nodes, setNodes] = useState<NodeRead[] | null>(null)

  useEffect(() => {
    void readNodeChildren(null).then((page) => setNodes(page.items))
  }, [])

  if (!nodes) return <Spinner aria-label="Loading library" />

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <CreateNodeSheet parentNodeId={null} />
      </div>
      <NodeList nodes={nodes} emptyAction={<CreateNodeSheet parentNodeId={null} />} />
    </div>
  )
}
