"use client";

import { use } from "react";
import { FlashcardDeck } from "@/components/study/flashcard";
import { useNode } from "@/lib/api-hooks/use-nodes";
import { useDeckTerms } from "@/lib/api-hooks/use-terms";
import { deckTermReadsToFlashcards } from "@/lib/adapters";

interface Props {
  params: Promise<{
    id: string;
  }>;
}

export default function FlashcardPage({ params }: Props) {
  const { id } = use(params);
  const { data: deck, isLoading: deckLoading } = useNode(id);
  const { data: rows = [], isLoading: termsLoading } = useDeckTerms(id);

  if (deckLoading || termsLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-muted-foreground">Loading flashcards…</p>
      </div>
    );
  }

  if (!deck) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <h2 className="text-2xl font-semibold mb-2">Deck not found</h2>
          <p className="text-muted-foreground">
            The requested deck could not be found.
          </p>
        </div>
      </div>
    );
  }

  const terms = deckTermReadsToFlashcards(rows);

  if (terms.length === 0) {
    return (
      <div className="flex items-center justify-center h-full p-6">
        <div className="text-center max-w-md">
          <h2 className="text-2xl font-semibold mb-2">No terms ready</h2>
          <p className="text-muted-foreground mb-4">
            Add some terms or wait for definitions to finish generating.
          </p>
        </div>
      </div>
    );
  }

  return <FlashcardDeck terms={terms} className="h-full" />;
}
