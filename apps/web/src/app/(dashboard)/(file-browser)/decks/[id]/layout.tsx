"use client";

import { use } from "react";
import { useNode, useNodeChildren } from "@/lib/api-hooks/use-nodes";

import { DeckHeader, StudyModes, RelatedDecks } from "@/components/study";

interface Props {
  children: React.ReactNode;
  params: Promise<{
    id: string;
  }>;
}

export default function DeckLayout({ children, params }: Props) {
  const { id } = use(params);
  const { data: deck, isLoading } = useNode(id);
  const { data: siblings } = useNodeChildren(deck?.parent_node_id ?? undefined);

  if (isLoading) {
    return null;
  }
  if (!deck) {
    return <div>Deck not found</div>;
  }

  const relatedDecks = (siblings ?? []).filter(
    (n) => n.id !== id && n.type === "DECK",
  );

  return (
    <div className="space-y-6">
      <DeckHeader deck={deck} />
      <StudyModes deckId={id} />

      {children}

      <RelatedDecks relatedDecks={relatedDecks} />
    </div>
  );
}
