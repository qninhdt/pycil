/**
 * Type definitions mirroring pycil-core schemas.
 */
export type NodeType = "FOLDER" | "DECK";

export interface BreadcrumbEntry {
  id: string;
  name: string;
  type: NodeType;
}

export interface NodeRead {
  id: string;
  type: NodeType;
  name: string;
  description: string | null;
  parent_node_id: string | null;
  visibility: "PRIVATE" | "PUBLIC";
  definition_count: number;
  is_starred: boolean;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
  breadcrumb: BreadcrumbEntry[];
}

export interface NodeCreate {
  type: NodeType;
  name: string;
  description?: string | null;
  parent_node_id?: string | null;
}

export interface NodeUpdate {
  name?: string;
  description?: string | null;
}

export interface TermAddRequest {
  value: string;
}

export interface TermRead {
  id: number;
  value: string;
  type: string;
  created_at: string;
  updated_at: string;
}

export interface TermAddResponse {
  term: TermRead;
  job_id: string | null;
}

export interface DefinitionRead {
  id: number;
  part_of_speech: string | null;
  cefr_level: string | null;
  canonical_meaning: string | null;
  synonyms: string[] | null;
  antonyms: string[] | null;
}

export interface DeckTermRead {
  term: TermRead;
  position: number;
  definition: DefinitionRead | null;
  job_id: string | null;
  job_status: string | null;
}

export interface MCQData {
  stem: string;
  options: string[];
  correct_index: number;
  explanation: string;
  distractor_rationale: string[];
}

export interface QuestionRead {
  id: string;
  definition_id: number;
  type: "MULTIPLE_CHOICE";
  data: MCQData;
  created_at: string;
}

export interface QuestionFetchResponse {
  question: QuestionRead | null;
  status: "ready" | "pending";
}

export interface QuestionCheckResponse {
  correct: boolean;
  explanation: string | null;
  correct_index: number;
}

export interface StartSessionResponse {
  session_id: string;
  deck_id: string;
  selected_count: number;
}

export interface SessionQuestionResponse {
  question: {
    id: string;
    definition_id: number;
    type: "MULTIPLE_CHOICE";
    data: MCQData;
  } | null;
  status: "ready" | "pending" | "session_complete";
  round_index: number;
  round_position: number;
  round_size: number;
}

export interface TermReviewedResult {
  definition_id: number;
  elo_old: number;
  elo_new: number;
  elo_delta: number;
  next_review_date: string;
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
