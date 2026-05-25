import { fetchJson } from "./base";
import type {
  QuestionCheckResponse,
  QuestionFetchResponse,
} from "@/types/domain";

export function fetchOrEnqueueQuestion(definitionId: number) {
  return fetchJson<QuestionFetchResponse>(
    `/definitions/${definitionId}/question`,
  );
}

export function checkAnswer(questionId: string, selectedIndex: number) {
  return fetchJson<QuestionCheckResponse>(`/questions/${questionId}/check`, {
    method: "POST",
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
}
