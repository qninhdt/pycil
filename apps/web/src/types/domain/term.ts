import type { ISODateString } from "./node";

export interface TermRead {
  id: number;
  value: string;
  type: string;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface TermAddRequest {
  value: string;
}

export interface TermAddResponse {
  term: TermRead;
  job_id: string | null;
}

export interface DeckTermRead {
  term: TermRead;
  position: number;
  definition: Record<string, unknown> | null;
  job_id: string | null;
  job_status: string | null;
}
