"use server";

import { createApiClient } from "@/lib/api/client";
import type { DashboardStatsRead } from "@/lib/api/types";
import { getSession } from "@/lib/auth/session";

export async function getDashboardStatsAction(): Promise<DashboardStatsRead | null> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    return null;
  }
  try {
    const client = createApiClient(session);
    return await client.getDashboardStats();
  } catch (err) {
    console.error("Failed to fetch dashboard stats:", err);
    return null;
  }
}
