import type { ISODateString, UUID } from "./node";
import type { MCQData } from "./question";

export interface StartSessionRequest {
  session_size?: number;
}

export interface StartSessionResponse {
  session_id: string;
  deck_id: UUID;
  selected_count: number;
}

export type SessionStatus = "ready" | "pending" | "session_complete";

export interface SessionQuestionPayload {
  id: UUID;
  type: string;
  data: MCQData | Record<string, unknown>;
}

export interface SessionQuestionResponse {
  question: SessionQuestionPayload | null;
  status: SessionStatus;
  round_index: number;
  round_position: number;
  round_size: number;
}

export interface SubmitAnswerRequest {
  question_id: UUID;
  selected_index: number;
}

export interface TermReviewedResult {
  definition_id: number;
  elo_old: number;
  elo_new: number;
  elo_delta: number;
  next_review_date: ISODateString;
  interval_seconds: number;
  mastery_level: number;
}

export interface SubmitAnswerResponse {
  correct: boolean;
  explanation: string | null;
  correct_index: number;
  round_complete: boolean;
  session_complete: boolean;
  term_reviewed: TermReviewedResult | null;
}
