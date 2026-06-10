import type { ISODateString, UUID } from "./node";
import type { MCQDataPublic } from "./question";

export interface StartSessionRequest {
  session_size?: number;
  theme_id?: string | null;
}

export interface StartSessionResponse {
  session_id: string;
  deck_id: UUID;
  selected_count: number;
}

export type SessionStatus = "ready" | "pending" | "session_complete";

export interface SessionQuestionPayload {
  id: UUID;
  // Backend + mock always populate this on a "ready" question; optional so the
  // post-answer reconstruction in the learn UI (which lacks it) still type-checks.
  definition_id?: number;
  type: string;
  data: MCQDataPublic | Record<string, unknown>;
}

export interface SessionQuestionResponse {
  question: SessionQuestionPayload | null;
  status: SessionStatus;
  round_index: number;
  round_position: number;
  round_size: number;
  theme?: string | null;
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
  // Generic grading fields (type-agnostic). reveal carries post-submit
  // disclosure such as MCQ distractor_rationale.
  score?: number;
  feedback?: string | null;
  reveal?: Record<string, unknown>;
}
