"use client"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { WifiSlashIcon } from "@/lib/icons"
import { useRealtimeConnectionState } from "@/lib/realtime/provider"
import { isUnsettled } from "@/lib/stores/activity-store"
import { useActivityStore } from "@/lib/stores/store-provider"

/**
 * Says the one true thing about a dropped connection, and only when it matters.
 *
 * A disconnect with nothing outstanding is not worth a word: the subscribe proxy
 * replays the latest snapshot and recovery is enabled, so reconnecting settles
 * whatever was in flight. What the learner cannot know is whether work finished
 * while the connection was down, so that is exactly what this states — and only
 * while some work is actually outstanding.
 */
export function RealtimeStateNotice() {
  const connectionState = useRealtimeConnectionState()
  const outstanding = useActivityStore((state) => state.tasks.some(isUnsettled))

  if (connectionState === "connected" || !outstanding) return null

  return (
    <Alert>
      <WifiSlashIcon />
      <AlertTitle>Not connected</AlertTitle>
      <AlertDescription>
        Work already running will finish. This list may be behind until the
        connection returns.
      </AlertDescription>
    </Alert>
  )
}
