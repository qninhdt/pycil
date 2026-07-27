"use client";

import { useEffect, useState } from "react";
import type { PublicationContext, SubscribedContext, Subscription } from "centrifuge";
import { useCentrifuge } from "./provider";
import { reduceAsyncTaskSnapshot, type AsyncTaskSnapshot } from "./task-snapshot";

export function useTaskSnapshot(taskId: string | null): AsyncTaskSnapshot | null {
  const centrifuge = useCentrifuge();
  const [snapshot, setSnapshot] = useState<AsyncTaskSnapshot | null>(null);

  useEffect(() => {
    setSnapshot(null);
    if (!centrifuge || !taskId) return;

    const channel = `async:${taskId}`;
    let subscription: Subscription | null = null;
    const applySnapshot = (data: unknown) => {
      setSnapshot((current) => reduceAsyncTaskSnapshot(current, data, taskId));
    };
    const onSubscribed = (context: SubscribedContext) => applySnapshot(context.data);
    const onPublication = (context: PublicationContext) => applySnapshot(context.data);

    try {
      subscription = centrifuge.getSubscription(channel) ?? centrifuge.newSubscription(channel);
      subscription.on("subscribed", onSubscribed);
      subscription.on("publication", onPublication);
      if (subscription.state === "unsubscribed") subscription.subscribe();
    } catch (error) {
      console.warn(`Failed to subscribe to async task ${taskId}:`, error);
    }

    return () => {
      if (!subscription) return;
      subscription.off("subscribed", onSubscribed);
      subscription.off("publication", onPublication);
      if (
        subscription.listeners("subscribed").length === 0 &&
        subscription.listeners("publication").length === 0
      ) {
        subscription.unsubscribe();
        centrifuge.removeSubscription(subscription);
      }
    };
  }, [centrifuge, taskId]);

  return snapshot;
}
