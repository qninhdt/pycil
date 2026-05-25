import type { DeckTermRead } from "@/types/domain";
import type { DeckTerm, Term } from "@/types/term";

interface DefinitionShape {
  canonical_meaning?: string;
  paraphrase?: string;
}

function pickDefinitionText(def: DeckTermRead["definition"]): string {
  if (!def) return "";
  const d = def as DefinitionShape;
  return d.canonical_meaning ?? d.paraphrase ?? "";
}

export function deckTermReadToDeckTerm(row: DeckTermRead): DeckTerm {
  const generating =
    row.job_status === "pending" || row.job_status === "running";
  return {
    id: String(row.term.id),
    term: row.term.value,
    definition: generating ? "" : pickDefinitionText(row.definition),
    mastered: false,
    difficulty: "medium",
    addedAt: row.term.created_at,
    isRecentlyAdded: false,
  };
}

export function deckTermReadsToDeckTerms(rows: DeckTermRead[]): DeckTerm[] {
  return rows.map(deckTermReadToDeckTerm);
}

export function deckTermReadsToFlashcards(rows: DeckTermRead[]): Term[] {
  return rows
    .filter((r) => r.definition && pickDefinitionText(r.definition))
    .map((r) => ({
      id: String(r.term.id),
      term: r.term.value,
      definition: pickDefinitionText(r.definition),
      mastered: false,
      difficulty: "medium" as const,
      addedAt: r.term.created_at,
      isRecentlyAdded: false,
    }));
}
