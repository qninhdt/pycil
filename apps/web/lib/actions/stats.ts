"use server";

import { createApiClient } from "@/lib/api/client";
import { getSession } from "@/lib/auth/session";
import type { CefrDistribution, HistoryBucketRead, WeakSenseRead } from "@/lib/api/types";

export async function getFolderWeakestAction(
  nodeId: string,
  limit = 10
): Promise<WeakSenseRead[]> {
  const session = await getSession();
  if (!session.isLoggedIn) return [];
  try {
    const client = createApiClient(session);
    return await client.getFolderWeakest(nodeId, limit);
  } catch (err) {
    console.error(`Failed to fetch weakest senses for ${nodeId}:`, err);
    return [];
  }
}

export async function getFolderCefrAction(nodeId: string): Promise<CefrDistribution> {
  const session = await getSession();
  try {
    const client = createApiClient(session);
    return await client.getFolderCefr(nodeId);
  } catch (err) {
    console.error(`Failed to fetch CEFR distribution for ${nodeId}:`, err);
    return {};
  }
}

export async function getFolderHistoryAction(
  nodeId: string,
  from?: string,
  to?: string
): Promise<HistoryBucketRead[]> {
  const session = await getSession();
  if (!session.isLoggedIn) return [];
  try {
    const client = createApiClient(session);
    return await client.getFolderHistory(nodeId, from, to);
  } catch (err) {
    console.error(`Failed to fetch history for ${nodeId}:`, err);
    return [];
  }
}
