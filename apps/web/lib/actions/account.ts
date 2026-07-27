"use server";

import { createApiClient } from "@/lib/api/client";
import type { AccountExport } from "@/lib/api/types";
import { getSession } from "@/lib/auth/session";

export async function exportAccountDataAction(): Promise<AccountExport | null> {
  const session = await getSession();
  if (!session.isLoggedIn) return null;
  try {
    const client = createApiClient(session);
    return await client.exportAccountData();
  } catch (err) {
    console.error("Failed to export account data:", err);
    return null;
  }
}

export async function deleteAccountAction(): Promise<{ success: boolean; error?: string }> {
  const session = await getSession();
  if (!session.isLoggedIn || !session.refreshToken) {
    return { success: false, error: "Authentication required" };
  }
  try {
    const client = createApiClient(session);
    await client.deleteAccount(session.refreshToken);
    session.destroy();
    return { success: true };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Account deletion failed";
    return { success: false, error: message };
  }
}
