"use client"

import { use, useEffect, useState } from "react"

import { QuestionStage } from "@/components/study/question-stage"
import { StartSessionPanel } from "@/components/study/start-session-panel"
import { readNode } from "@/lib/actions/library-reads"
import type { NodeRead } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

export default function StartStudyPage({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = use(params)
  const [node, setNode] = useState<NodeRead | null | undefined>(undefined)
  useEffect(() => {
    void readNode(nodeId).then(setNode)
  }, [nodeId])

  if (node === undefined) return <Spinner aria-label="Loading study" />
  if (!node) return <p className="text-sm text-muted-foreground">This item is not available.</p>
  // A reference is a link, not a study source: the learner should study the target
  // itself, so the panel is not offered for one.
  if (node.type === "REFERENCE") {
    return <p className="text-sm text-muted-foreground">Open the linked item to study it.</p>
  }
  return (
    <QuestionStage>
      <StartSessionPanel
        nodeId={nodeId}
        nodeName={node.name}
        nodeType={node.type}
        itemCount={node.itemCount ?? null}
      />
    </QuestionStage>
  )
}
