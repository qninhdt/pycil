import "server-only"

import { createApiClient } from "@/lib/api/client"
import type { DashboardStatsRead, WeakSenseRead } from "@/lib/api/types"
import { getSession } from "@/lib/auth/session"

/**
 * Today's two reads, fetched on the server for the page that renders them.
 *
 * These are not server actions: nothing mutates and nothing calls them from the
 * browser, so they stay plain server-only functions. Marking them `"use server"`
 * would publish two callable endpoints for no reason.
 */

export interface TodayData {
  stats: DashboardStatsRead
  weakest: WeakSenseRead[]
}

export async function getTodayData(): Promise<TodayData> {
  const session = await getSession()
  const client = createApiClient(session)

  // Both reads are independent, so they overlap rather than queue. An error in
  // either is left to propagate: the route's error boundary states it once
  // instead of every block rendering its own half-empty guess.
  const [stats, weakest] = await Promise.all([
    client.getDashboardStats(),
    client.getGlobalWeakest(5),
  ])

  return { stats, weakest }
}
