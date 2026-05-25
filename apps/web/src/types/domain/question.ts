import type { ISODateString, UUID } from "./node";

export type QuestionStatus = "ready" | "pending";

export interface MCQData {
  stem: string;
  options: [string, string, string, string];
  correct_index: number;
  explanation: string;
  distractor_rationale: [string, string, string];
}

export interface QuestionRead {
  id: UUID;
  definition_id: number;
  type: string;
  data: MCQData | Record<string, unknown>;
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
