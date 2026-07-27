"use server";

import { createApiClient } from "@/lib/api/client";
import type {
  FolderStats,
  GradeResponse,
  NextQuestionResponse,
  SessionStartResponse,
} from "@/lib/api/types";
import { getSession } from "@/lib/auth/session";

export async function startStudySessionAction(
  nodeId: string
): Promise<SessionStartResponse> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    throw new Error("unauthorized");
  }
  const client = createApiClient(session);
  return await client.startSession(nodeId);
}

export async function getNextQuestionAction(
  sessionId: string
): Promise<NextQuestionResponse> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    throw new Error("unauthorized");
  }
  const client = createApiClient(session);
  return await client.getNextQuestion(sessionId);
}

export async function submitAnswerAction(
  sessionId: string,
  questionId: string,
  answer: string
): Promise<GradeResponse> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    throw new Error("unauthorized");
  }
  const client = createApiClient(session);
  return await client.submitAnswer(sessionId, questionId, answer);
}

export async function getFolderStatsAction(
  nodeId: string
): Promise<FolderStats | null> {
  const session = await getSession();
  if (!session.isLoggedIn) {
    return null;
  }
  try {
    const client = createApiClient(session);
    return await client.getFolderStats(nodeId);
  } catch (err) {
    console.warn(`Failed to fetch folder stats for ${nodeId}:`, err);
    return null;
  }
}
