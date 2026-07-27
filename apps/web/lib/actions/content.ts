"use server";

import { createApiClient } from "@/lib/api/client";
import { getSession } from "@/lib/auth/session";
import type { GenerationCreateRead, SenseAddResponse, WordSearchRead } from "@/lib/api/types";

export async function searchWords(query: string): Promise<WordSearchRead[]> {
  if (!query || !query.trim()) return [];
  const session = await getSession();
  const client = createApiClient(session);
  return await client.searchWords(query.trim());
}

export async function submitWordGeneration(query: string): Promise<GenerationCreateRead> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    throw new Error("unauthorized");
  }
  const client = createApiClient(session);
  return await client.submitWordGeneration(query.trim());
}

export async function addSenseToDeck(nodeId: string, senseId: number): Promise<SenseAddResponse> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    throw new Error("unauthorized");
  }
  const client = createApiClient(session);
  return await client.addSenseToDeck(nodeId, senseId);
}

export async function updateDeckSettingsAction(
  nodeId: string,
  settings: { newPerBatch?: number; reviewPerBatch?: number }
) {
  const session = await getSession();
  if (!session.isLoggedIn) throw new Error("unauthorized");
  const client = createApiClient(session);
  return await client.updateDeckSettings(nodeId, settings);
}

export async function getFolderItemsAction(nodeId: string, offset = 0, limit = 50) {
  const session = await getSession();
  const client = createApiClient(session);
  return await client.getFolderItems(nodeId, offset, limit);
}
