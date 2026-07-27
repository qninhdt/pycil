"use server";

import { createApiClient } from "@/lib/api/client";
import { getSession } from "@/lib/auth/session";

export async function getMe() {
  const session = await getSession();
  if (!session.isLoggedIn) return null;
  const client = createApiClient(session);
  return client.getMe();
}

export async function getCapabilities() {
  const session = await getSession();
  const client = createApiClient(session);
  return client.getCapabilities();
}
