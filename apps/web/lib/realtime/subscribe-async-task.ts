import type { Centrifuge, Subscription } from "centrifuge"

import { ASYNC_TASK_NAMESPACE } from "./grading-result.generated"
import { isAsyncTaskSnapshot, type AsyncTaskSnapshot } from "./task-snapshot"

/** Centrifugo's permission-denied code, returned by the subscribe proxy. */
const PERMISSION_DENIED = 103

export interface AsyncTaskSubscriptionHandlers {
  /**
   * Called for the snapshot replayed on subscribe and for every publication
   * after it. Ordering is not guaranteed, so callers must compare `version`.
   */
  onSnapshot: (snapshot: AsyncTaskSnapshot) => void
  /**
   * Called only when the subscribe proxy *denies* the channel. A transport
   * error is not a denial: recovery is enabled and the proxy replays the latest
   * snapshot, so a reconnect settles the task on its own.
   */
  onDenied?: () => void
}

/**
 * Subscribes to one async task channel and returns the teardown.
 *
 * Subscriptions are shared per channel because two surfaces can watch the same
 * task at once — the activity centre and the screen that started the work.
 * Centrifuge rejects a second `newSubscription` for a live channel, so the
 * existing one is reused and only torn down once its last listener leaves.
 */
export function subscribeToAsyncTask(
  centrifuge: Centrifuge,
  taskId: string,
  handlers: AsyncTaskSubscriptionHandlers,
): () => void {
  const channel = `${ASYNC_TASK_NAMESPACE}:${taskId}`
  let subscription: Subscription

  try {
    subscription =
      centrifuge.getSubscription(channel) ?? centrifuge.newSubscription(channel)
  } catch (error) {
    if (process.env.NODE_ENV === "development") {
      console.warn(`could not subscribe to ${channel}`, error)
    }
    return () => {}
  }

  const apply = (data: unknown) => {
    if (isAsyncTaskSnapshot(data) && data.taskId === taskId) handlers.onSnapshot(data)
  }
  const onSubscribed = (context: { data?: unknown }) => apply(context.data)
  const onPublication = (context: { data: unknown }) => apply(context.data)
  const onError = (context: { error: { code: number } }) => {
    if (context.error.code === PERMISSION_DENIED) handlers.onDenied?.()
  }

  subscription.on("subscribed", onSubscribed)
  subscription.on("publication", onPublication)
  subscription.on("error", onError)
  if (subscription.state === "unsubscribed") subscription.subscribe()

  return () => {
    subscription.off("subscribed", onSubscribed)
    subscription.off("publication", onPublication)
    subscription.off("error", onError)
    if (
      subscription.listeners("subscribed").length === 0 &&
      subscription.listeners("publication").length === 0
    ) {
      subscription.unsubscribe()
      centrifuge.removeSubscription(subscription)
    }
  }
}
