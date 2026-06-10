import { fetchJson } from "./base";
import type {
  ApplyVerdictRequest,
  SessionQuestionResponse,
  StartSessionRequest,
  StartSessionResponse,
  SubmitAnswerRequest,
  SubmitAnswerResponse,
  UUID,
} from "@/types/domain";

export function startSession(deckId: UUID, body: StartSessionRequest = {}) {
  return fetchJson<StartSessionResponse>(`/decks/${deckId}/learn`, {
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

export function applyVerdict(sessionId: string, body: ApplyVerdictRequest) {
  return fetchJson<SubmitAnswerResponse>(
    `/sessions/${sessionId}/apply-verdict`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
}
