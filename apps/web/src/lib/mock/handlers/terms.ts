// Mock handlers for /decks/:id/terms — mirrors routes/terms.py.
// Enrichment completes synchronously (no job/SSE), so definitions are present
// immediately and job_status reads "completed".

import { getState, commit } from "../store";
import { nextInt } from "../id";
import type { StoreDefinition, StoreTerm } from "../types";
import type { DeckTermRead, TermAddResponse, TermRead } from "@/types/domain";

function nowIso(): string {
  return new Date().toISOString();
}

function toTermRead(t: StoreTerm): TermRead {
  return {
    id: t.id,
    value: t.value,
    type: t.type,
    created_at: t.created_at,
    updated_at: t.updated_at,
  };
}

function definitionPayload(def: StoreDefinition | undefined) {
  if (!def) return null;
  return {
    id: def.id,
    canonical_meaning: def.canonical_meaning,
    paraphrase: def.paraphrase,
    example: def.example,
    part_of_speech: def.part_of_speech,
  };
}

export function listDeckTerms(deckId: string): DeckTermRead[] {
  const { terms, definitions } = getState();
  return Object.values(terms)
    .filter((t) => t.deck_id === deckId)
    .sort((a, b) => a.position - b.position)
    .map((t) => ({
      term: toTermRead(t),
      position: t.position,
      definition: t.definition_id
        ? definitionPayload(definitions[t.definition_id])
        : null,
      job_id: null,
      job_status: t.definition_id ? "completed" : null,
    }));
}

export function addTerm(deckId: string, value: string): TermAddResponse {
  const state = getState();
  const ts = nowIso();
  const defId = nextInt();
  const termId = nextInt();

  // Synchronous enrichment: attach a generic-but-plausible definition + MCQ.
  const def: StoreDefinition = {
    id: defId,
    canonical_meaning: `Definition for "${value}".`,
    paraphrase: `A word meaning related to ${value}.`,
    example: `This is an example sentence using ${value}.`,
    part_of_speech: "noun",
  };
  state.definitions[defId] = def;

  const existing = Object.values(state.terms).filter(
    (t) => t.deck_id === deckId,
  );
  const term: StoreTerm = {
    id: termId,
    deck_id: deckId,
    value,
    type: "noun",
    position: existing.length,
    definition_id: defId,
    created_at: ts,
    updated_at: ts,
  };
  state.terms[termId] = term;

  // Pre-bake an MCQ for the new definition so study mode works immediately.
  const qId = `q-${defId}`;
  state.questions[qId] = {
    id: qId,
    definition_id: defId,
    type: "MCQ",
    stem: `What does "${value}" mean?`,
    options: [
      def.canonical_meaning,
      "An unrelated meaning A.",
      "An unrelated meaning B.",
      "An unrelated meaning C.",
    ],
    correct_index: 0,
    explanation: `"${value}" means: ${def.canonical_meaning}`,
    distractor_rationale: [
      "Unrelated A",
      "Unrelated B",
      "Unrelated C",
    ],
    created_at: ts,
  };
  state.questionByDefinition[defId] = qId;

  commit();
  return { term: toTermRead(term), job_id: null };
}
