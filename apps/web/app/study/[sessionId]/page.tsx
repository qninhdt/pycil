"use client"

import { use, useEffect, useState } from "react"

import { SessionRunner } from "@/components/study/session-runner"
import { readNode } from "@/lib/actions/library-reads"
import { readSession } from "@/lib/actions/study"
import type { SessionState } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

export default function StudySessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params)
  const [session, setSession] = useState<SessionState | null | undefined>(undefined)
  const [deckTitle, setDeckTitle] = useState("this deck")

  useEffect(() => {
    let active = true
    void readSession(sessionId).then(async (result) => {
      if (!active) return
      if (!result.success) {
        setSession(null)
        return
      }
      setSession(result.data)
      if (result.data.nodeId) {
        const node = await readNode(result.data.nodeId)
        if (active && node) setDeckTitle(node.name)
      }
    })
    return () => {
      active = false
    }
  }, [sessionId])

  if (session === undefined) return <Spinner aria-label="Loading study session" />
  if (!session) return <p className="text-sm text-muted-foreground">This session is not available.</p>
  return <SessionRunner sessionId={sessionId} initialSession={session} deckTitle={deckTitle} />
}
