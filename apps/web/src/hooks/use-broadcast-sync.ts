"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Cross-tab cache invalidation via BroadcastChannel.
 *
 * Call `useBroadcastSync()` in a top-level provider (e.g. `app/providers.tsx`)
 * to subscribe; call `broadcastInvalidate(['nodes'])` after mutations to
 * notify other tabs to refetch.
 *
 * Falls back to no-op when BroadcastChannel is unsupported (Safari <16).
 */
const CHANNEL = "pycil-sync";

export function useBroadcastSync() {
  const qc = useQueryClient();

  useEffect(() => {
    if (typeof window === "undefined" || !("BroadcastChannel" in window)) {
      return;
    }
    const ch = new BroadcastChannel(CHANNEL);
    ch.onmessage = (ev) => {
      const data = ev.data as { type?: string; queryKey?: unknown[] } | null;
      if (data?.type === "invalidate" && Array.isArray(data.queryKey)) {
        qc.invalidateQueries({ queryKey: data.queryKey });
      }
    };
    return () => ch.close();
  }, [qc]);
}

export function broadcastInvalidate(queryKey: unknown[]): void {
  if (typeof window === "undefined" || !("BroadcastChannel" in window)) {
    return;
  }
  const ch = new BroadcastChannel(CHANNEL);
  try {
    ch.postMessage({ type: "invalidate", queryKey });
  } finally {
    ch.close();
  }
}
