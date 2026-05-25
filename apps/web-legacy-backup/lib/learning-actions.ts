/** Server actions for the learning session API. */
"use server";

import { api } from "@/lib/api";
import type {
  SessionQuestionResponse,
  StartSessionResponse,
  SubmitAnswerResponse,
} from "@/lib/types";

export async function startSessionAction(
  deckId: string,
  sessionSize = 20
): Promise<StartSessionResponse> {
  return api<StartSessionResponse>(`/decks/${deckId}/learn`, {
    method: "POST",
    body: JSON.stringify({ session_size: sessionSize }),
  });
}

export async function nextQuestionAction(
  sessionId: string
): Promise<SessionQuestionResponse> {
  return api<SessionQuestionResponse>(`/sessions/${sessionId}/question`);
}

export async function submitAnswerAction(
  sessionId: string,
  questionId: string,
  selectedIndex: number
): Promise<SubmitAnswerResponse> {
  return api<SubmitAnswerResponse>(`/sessions/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify({
      question_id: questionId,
      selected_index: selectedIndex,
    }),
  });
}
