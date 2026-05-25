/**
 * Client wrapper for the question API.
 *
 * Run from server components / route handlers — pass the user cookie
 * through, same pattern as `lib/api.ts`.
 */
import { api } from "@/lib/api";
import type {
  QuestionCheckResponse,
  QuestionFetchResponse,
} from "@/lib/types";

export async function fetchQuestion(
  definitionId: number,
  difficulty: "easy" | "medium" | "hard" = "easy"
): Promise<QuestionFetchResponse> {
  return api<QuestionFetchResponse>(
    `/definitions/${definitionId}/question?difficulty=${difficulty}`
  );
}

export async function checkAnswer(
  questionId: string,
  selectedIndex: number
): Promise<QuestionCheckResponse> {
  return api<QuestionCheckResponse>(`/questions/${questionId}/check`, {
    method: "POST",
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
}
