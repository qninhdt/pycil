"use client"

import { useEffect } from "react"

import { isUnsettled } from "@/lib/stores/activity-store"
import { useActivityActions, useActivityStore } from "@/lib/stores/store-provider"

import { useCentrifuge } from "./provider"
import { subscribeToAsyncTask } from "./subscribe-async-task"

/**
 * Keeps a subscription open for every task the activity store still considers
 * unsettled, including the ones restored from a reload. Mounted once, next to
 * the activity centre.
 *
 * Nothing polls: the subscribe proxy replays the latest persisted snapshot, so
 * subscribing *is* the read. That also means a task settled while the tab was
 * closed settles here on the next mount.
 */
export function useActivitySubscriptions() {
  const centrifuge = useCentrifuge()
  const { applySnapshot, markStale } = useActivityActions()
  // Depending on the id list rather than the task objects keeps this effect from
  // tearing down every subscription each time a status changes.
  const outstandingIds = useActivityStore((state) =>
    state.tasks
      .filter(isUnsettled)
      .map((task) => task.taskId)
      .join(","),
  )

  useEffect(() => {
    if (!centrifuge || outstandingIds.length === 0) return

    const teardowns = outstandingIds.split(",").map((taskId) =>
      subscribeToAsyncTask(centrifuge, taskId, {
        onSnapshot: applySnapshot,
        onDenied: () => markStale(taskId),
      }),
    )

    return () => teardowns.forEach((teardown) => teardown())
  }, [centrifuge, outstandingIds, applySnapshot, markStale])
}
