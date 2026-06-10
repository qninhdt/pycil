import { fetchJson } from "./base";

export type PublicDeck = {
  id: string;
  name: string;
  description: string | null;
  term_count: number;
  clone_count: number;
};

export function listPublicDecks(q?: string) {
  const url = q
    ? `/public/decks?q=${encodeURIComponent(q)}`
    : "/public/decks";
  return fetchJson<{ decks: PublicDeck[] }>(url);
}

export function clonePublicDeck(deckId: string) {
  return fetchJson<{ new_deck_id: string }>(
    `/public/decks/${deckId}/clone`,
    { method: "POST" },
  );
}
