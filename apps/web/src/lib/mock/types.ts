// Internal mock store entity shapes. Supersets of the API read schemas so the
// handlers can return schema-faithful payloads while keeping extra bookkeeping
// fields (e.g. session cursor, per-definition correct_index) private.

import type {
  BreadcrumbEntry,
  CurrentUser,
  NodeType,
} from "@/types/domain";

export interface StoreNode {
  id: string;
  type: NodeType;
  name: string;
  description: string | null;
  parent_node_id: string | null;
  target_node_id?: string | null;
  visibility: "PRIVATE" | "PUBLIC";
  is_starred: boolean;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface StoreDefinition {
  id: number;
  canonical_meaning: string;
  paraphrase: string;
  example: string;
  part_of_speech: string;
}

export interface StoreTerm {
  id: number;
  deck_id: string;
  value: string;
  type: string;
  position: number;
  definition_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface StoreQuestion {
  id: string;
  definition_id: number;
  type: string;
  stem: string;
  options: [string, string, string, string];
  correct_index: number;
  explanation: string;
  distractor_rationale: [string, string, string];
  created_at: string;
}

export interface StoreSession {
  id: string;
  deck_id: string;
  // ordered definition ids selected for the session
  definition_ids: number[];
  cursor: number;
  round_index: number;
  // cursor index where the current round began (rounds are ROUND_SIZE long)
  round_start: number;
  answered: number;
  correct: number;
}

export interface StoreUser extends CurrentUser {
  bio?: string;
  study_settings?: Record<string, unknown>;
}

export interface MockState {
  user: StoreUser;
  nodes: Record<string, StoreNode>;
  terms: Record<number, StoreTerm>;
  definitions: Record<number, StoreDefinition>;
  questions: Record<string, StoreQuestion>;
  // questions keyed by definition id for fast lookup
  questionByDefinition: Record<number, string>;
  sessions: Record<string, StoreSession>;
  intSeed: number;
}

export type { BreadcrumbEntry };
