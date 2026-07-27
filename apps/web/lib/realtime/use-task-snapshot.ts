"use client"

import { useEffect, useState } from "react"

import { useCentrifuge } from "./provider"
import { subscribeToAsyncTask } from "./subscribe-async-task"
import { reduceAsyncTaskSnapshot, type AsyncTaskSnapshot } from "./task-snapshot"

/**
 * Watches one task for the screen that started it. The activity centre watches
 * the same channel independently; sharing is handled inside the subscribe
 * helper, so both can mount without fighting over the subscription.
 */
export function useTaskSnapshot(taskId: string | null): AsyncTaskSnapshot | null {
  const centrifuge = useCentrifuge()
  // The watched id is held next to the snapshot so switching tasks resets the
  // result by derivation rather than by a setState in an effect. Clearing it in
  // the effect would render the previous task's verdict for one frame first,
  // which on a grade means briefly showing the wrong answer as this one's.
  const [held, setHeld] = useState<{
    taskId: string | null
    snapshot: AsyncTaskSnapshot | null
  }>({ taskId, snapshot: null })

  useEffect(() => {
    if (!centrifuge || !taskId) return

    return subscribeToAsyncTask(centrifuge, taskId, {
      // The reducer, not the setter, decides what wins: a replayed snapshot on
      // re-subscribe can arrive after a newer publication.
      onSnapshot: (incoming) =>
        setHeld((current) => ({
          taskId,
          snapshot: reduceAsyncTaskSnapshot(
            current.taskId === taskId ? current.snapshot : null,
            incoming,
            taskId,
          ),
        })),
    })
  }, [centrifuge, taskId])

  return held.taskId === taskId ? held.snapshot : null
}
