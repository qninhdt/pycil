"use client"

import { useEffect } from "react"

import { createApiClient } from "@/lib/api/client"
import { isUnsettled } from "@/lib/stores/activity-store"
import { useActivityActions, useActivityStore } from "@/lib/stores/store-provider"

const DELAYS = [600, 1200, 2400, 4000]

/** Polls canonical Postgres job snapshots; no push service is involved. */
export function useActivitySubscriptions() {
  const { applySnapshot, markStale } = useActivityActions()
  const tasks = useActivityStore((state) => state.tasks)
  const ids = tasks.filter(isUnsettled).map((task) => task.taskId).join(",")

  useEffect(() => {
    if (!ids) return
    let active = true
    const client = createApiClient()
    const timers: ReturnType<typeof setTimeout>[] = []

    for (const taskId of ids.split(",")) {
      let attempt = 0
      const poll = async () => {
        try {
          const snapshot = await client.jobs.get(taskId)
          if (!active) return
          applySnapshot(snapshot)
          if (snapshot.status === "queued" || snapshot.status === "running") {
            timers.push(setTimeout(poll, DELAYS[Math.min(attempt++, DELAYS.length - 1)]))
          }
        } catch {
          if (active) {
            markStale(taskId)
            timers.push(setTimeout(poll, DELAYS[Math.min(attempt++, DELAYS.length - 1)]))
          }
        }
      }
      void poll()
    }

    return () => {
      active = false
      timers.forEach(clearTimeout)
    }
  }, [applySnapshot, ids, markStale])
}
