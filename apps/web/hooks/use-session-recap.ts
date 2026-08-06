"use client"

import { useEffect, useState } from "react"

import { readSession } from "@/lib/actions/study"
import type { SessionState } from "@/lib/api/types"

/**
 * The session's own summary, once it has finished.
 *
 * Read from the server rather than accumulated on the client. Reaching `exhausted`
 * deletes the live Redis namespace, so only the persisted summary is left — and
 * reading it is what makes the recap survive a reload rather than being state a
 * refresh would discard.
 *
 * A session that was already complete when the page loaded has its recap in hand, so
 * it never fetches; that is the seed argument rather than a special case at the call
 * site.
 */
export function useSessionRecap({
  sessionId,
  finished,
  initial,
}: {
  sessionId: string
  finished: boolean
  /** The recap already in hand, for a session that was complete on load. */
  initial: SessionState | null
}): SessionState | null {
  const [recap, setRecap] = useState<SessionState | null>(initial)

  useEffect(() => {
    if (!finished || recap) return
    let active = true
    void readSession(sessionId).then((result) => {
      if (active && result.success) setRecap(result.data)
    })
    return () => {
      active = false
    }
  }, [finished, recap, sessionId])

  return recap
}
