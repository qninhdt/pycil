"use server";

import { createApiClient } from "@/lib/api/client";
import { SessionPersistenceError } from "@/lib/api/request";
import { getSession } from "@/lib/auth/session";

export async function getRealtimeToken() {
  const session = await getSession();
  if (!session.isLoggedIn) return null;
  try {
    const client = createApiClient(session, { refresh: true });
    return await client.auth.getRealtimeToken();
  } catch (err) {
    if (err instanceof SessionPersistenceError) {
      console.error("Failed to persist session while fetching realtime token:", err);
      throw err;
    }
    console.warn("Failed to fetch realtime token:", err);
    return null;
  }
}
