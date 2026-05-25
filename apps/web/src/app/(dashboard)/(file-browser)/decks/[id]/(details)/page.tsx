"use client";

import { use } from "react";
import { StudyProgress, FlashcardDeck } from "@/components/study";
import type { StudyProgressData } from "@/types";
import { useNode } from "@/lib/api-hooks/use-nodes";
import { useDeckTerms } from "@/lib/api-hooks/use-terms";
import { deckTermReadsToDeckTerms } from "@/lib/adapters";

interface Props {
  params: Promise<{ id: string }>;
}

export default function TermDeckOverviewPage({ params }: Props) {
  const { id } = use(params);
  const { data: deck, isLoading: deckLoading } = useNode(id);
  const { data: rows = [], isLoading: termsLoading } = useDeckTerms(id);

  const terms = deckTermReadsToDeckTerms(rows).slice(0, 5);

  const studyProgress: StudyProgressData = {
    newCards: terms.length,
    stillLearning: 0,
    almostDone: 0,
    mastered: 0,
  };

  if (deckLoading || termsLoading) {
    return <p className="text-sm text-muted-foreground">Loading deck…</p>;
  }
  if (!deck) {
    return <div>Deck not found</div>;
  }

  return (
    <div className="space-y-6">
      <FlashcardDeck terms={terms} className="md:aspect-[16/9] aspect-[4/3]" />
      <StudyProgress studyProgress={studyProgress} />
    </div>
  );
}
