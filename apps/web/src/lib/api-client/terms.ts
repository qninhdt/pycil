import { fetchJson } from "./base";
import type { DeckTermRead, TermAddResponse, UUID } from "@/types/domain";

export function listDeckTerms(deckId: UUID) {
  return fetchJson<DeckTermRead[]>(`/decks/${deckId}/terms`);
}

export function addTerm(deckId: UUID, value: string) {
  return fetchJson<TermAddResponse>(`/decks/${deckId}/terms`, {
    method: "POST",
    body: JSON.stringify({ value }),
  });
}
