import { createApiClient } from "@/lib/api/client"
import type { DashboardStats, WeakSense } from "@/lib/api/types"

/**
 * Today's two direct API reads.
 *
 * Nothing mutates, so this remains a small browser-callable read wrapper.
 */

export interface TodayData {
  stats: DashboardStats
  weakest: WeakSense[]
}

export async function getTodayData(): Promise<TodayData> {
  const client = createApiClient()

  // Both reads are independent, so they overlap rather than queue. An error in
  // either is left to propagate: the route's error boundary states it once
  // instead of every block rendering its own half-empty guess.
  const [stats, weakest] = await Promise.all([
    client.analytics.getDashboard(),
    client.analytics.getGlobalWeakest(5),
  ])

  return { stats, weakest }
}
