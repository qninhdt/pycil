import type { ISODateString, UUID } from "./node";

export type QuestionStatus = "ready" | "pending";

/** Pre-submit projection: never includes answer fields. BE always strips. */
export interface MCQDataPublic {
  stem: string;
  options: [string, string, string, string];
}

/** Post-submit reveal: returned by `POST /questions/{id}/check` only. */
export interface MCQDataReveal extends MCQDataPublic {
  correct_index: number;
  explanation: string;
  distractor_rationale: [string, string, string];
}

export interface QuestionRead {
  id: UUID;
  definition_id: number;
  type: string;
  data: MCQDataPublic | Record<string, unknown>;
  created_at: ISODateString;
}

export interface QuestionFetchResponse {
  question: QuestionRead | null;
  status: QuestionStatus;
}

export interface QuestionCheckRequest {
  selected_index: number;
}

export interface QuestionCheckResponse {
  correct: boolean;
  explanation: string | null;
  correct_index: number;
}
