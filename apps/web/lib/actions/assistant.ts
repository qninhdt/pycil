"use server";

import { createApiClient } from "@/lib/api/client";
import type { AssistantRunEvent, AssistantThread } from "@/lib/api/types";
import { getSession } from "@/lib/auth/session";

export async function listThreadsAction(): Promise<AssistantThread[]> {
  const session = await getSession();
  if (!session.isLoggedIn) return [];
  try {
    const client = createApiClient(session);
    return await client.listAssistantThreads();
  } catch (err) {
    console.error("Failed to list threads:", err);
    return [];
  }
}

export async function createThreadAction(title?: string): Promise<AssistantThread | null> {
  const session = await getSession();
  if (!session.isLoggedIn) return null;
  try {
    const client = createApiClient(session);
    return await client.createAssistantThread(title);
  } catch (err) {
    console.error("Failed to create thread:", err);
    return null;
  }
}

export async function getThreadMessagesAction(threadId: string): Promise<AssistantRunEvent[]> {
  const session = await getSession();
  if (!session.isLoggedIn) return [];
  try {
    const client = createApiClient(session);
    return await client.getThreadMessages(threadId);
  } catch (err) {
    console.error("Failed to fetch thread messages:", err);
    return [];
  }
}

export async function confirmActionAction(
  threadId: string,
  actionId: string,
  decision: "approve" | "reject"
): Promise<boolean> {
  const session = await getSession();
  if (!session.isLoggedIn) return false;
  try {
    const client = createApiClient(session);
    await client.confirmAssistantAction(threadId, actionId, decision);
    return true;
  } catch (err) {
    console.error("Failed to confirm assistant action:", err);
    return false;
  }
}

export async function deleteThreadAction(threadId: string): Promise<boolean> {
  const session = await getSession();
  if (!session.isLoggedIn) return false;
  try {
    const client = createApiClient(session);
    await client.deleteAssistantThread(threadId);
    return true;
  } catch (err) {
    console.error("Failed to delete thread:", err);
    return false;
  }
}
