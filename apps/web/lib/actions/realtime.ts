"use server";

import { createApiClient } from "@/lib/api/client";
import { getSession } from "@/lib/auth/session";

export async function getRealtimeToken() {
  const session = await getSession();
  if (!session.isLoggedIn) return null;
  try {
    const client = createApiClient(session);
    return await client.getRealtimeToken();
  } catch (err) {
    console.warn("Failed to fetch realtime token:", err);
    return null;
  }
}
