import { fetchJson } from "./base";
import type {
  SessionQuestionResponse,
  StartSessionRequest,
  StartSessionResponse,
  SubmitAnswerRequest,
  SubmitAnswerResponse,
  UUID,
} from "@/types/domain";

export function startSession(deckId: UUID, body: StartSessionRequest = {}) {
  return fetchJson<StartSessionResponse>(`/decks/${deckId}/sessions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSessionQuestion(sessionId: string) {
  return fetchJson<SessionQuestionResponse>(`/sessions/${sessionId}/question`);
}

export function submitAnswer(sessionId: string, body: SubmitAnswerRequest) {
  return fetchJson<SubmitAnswerResponse>(`/sessions/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}
