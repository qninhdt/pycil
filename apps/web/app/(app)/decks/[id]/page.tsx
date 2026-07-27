"use client";

import { use, useState } from "react";
import { BookOpen, Search, Plus } from "lucide-react";
import Link from "next/link";
import { useNodeDetail } from "@/lib/query/nodes";
import { useDeckItems, useRemoveSenseFromDeck } from "@/lib/query/decks";
import { DeckHeader } from "@/components/decks/deck-header";
import { SenseItemCard } from "@/components/decks/sense-item-card";
import { WordSearchModal } from "@/components/decks/word-search-modal";
import { CefrDistributionChart } from "@/components/analytics/cefr-distribution-chart";
import { FolderHistoryChart } from "@/components/analytics/folder-history-chart";
import { WeakestWordsCard } from "@/components/dashboard/weakest-words-card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

export default function DeckDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [searchQuery, setSearchQuery] = useState("");
  const [addWordModalOpen, setAddWordModalOpen] = useState(false);

  const { data: deck, isLoading: isLoadingDeck } = useNodeDetail(id);
  const { data: items = [], isLoading: isLoadingItems } = useDeckItems(id);
  const removeSense = useRemoveSenseFromDeck();

  const handleRemoveSense = (senseId: number) => {
    removeSense.mutate({ deckId: id, senseId });
  };

  const filteredItems = items.filter((item) =>
    item.definition.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (item.pos && item.pos.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (item.examples && item.examples.some((ex) => ex.toLowerCase().includes(searchQuery.toLowerCase())))
  );

  const avgMastery =
    items.length > 0
      ? Math.round(
          items.reduce((sum, item) => sum + (item.mastery || 0), 0) / items.length
        )
      : 0;

  if (isLoadingDeck || isLoadingItems) {
    return (
      <div className="container max-w-6xl mx-auto p-6 space-y-6">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="space-y-4">
          <Skeleton className="h-10 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  if (!deck) {
    return (
      <div className="container max-w-6xl mx-auto p-6 text-center pt-12">
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Deck Not Found</EmptyTitle>
            <EmptyDescription>
              The deck you are looking for does not exist or you do not have permission to view it.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button render={<Link href="/library" />} className="mt-4">
              Return to Library
            </Button>
          </EmptyContent>
        </Empty>
      </div>
    );
  }

  return (
    <div className="container max-w-6xl mx-auto p-6 space-y-6">
      <DeckHeader
        deck={deck}
        totalItems={items.length}
        avgMastery={avgMastery}
        onAddWordClick={() => setAddWordModalOpen(true)}
      />

      {/* Analytics & Weak Words Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CefrDistributionChart nodeId={id} />
        <WeakestWordsCard nodeId={id} />
      </div>

      <FolderHistoryChart nodeId={id} />

      <div className="flex items-center gap-3 bg-card p-2 rounded-xl border border-border/50">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search words, definitions, examples..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 bg-background/50 border-0 focus-visible:ring-1"
          />
        </div>
      </div>

      {filteredItems.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredItems.map((item) => (
            <SenseItemCard
              key={item.senseId}
              item={item}
              onRemove={handleRemoveSense}
              isRemoving={removeSense.isPending}
            />
          ))}
        </div>
      ) : (
        <div className="pt-6">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <BookOpen className="h-6 w-6 text-muted-foreground" />
              </EmptyMedia>
              <EmptyTitle>
                {searchQuery ? "No matching words found" : "No words in this deck yet"}
              </EmptyTitle>
              <EmptyDescription>
                {searchQuery
                  ? "Try searching for a different definition or keyword."
                  : "Add words to this deck using the dictionary search."}
              </EmptyDescription>
            </EmptyHeader>
            {!searchQuery && (
              <EmptyContent>
                <Button onClick={() => setAddWordModalOpen(true)} className="mt-2">
                  <span className="flex items-center gap-1.5">
                    <Plus className="h-4 w-4" />
                    <span>Thêm từ mới</span>
                  </span>
                </Button>
              </EmptyContent>
            )}
          </Empty>
        </div>
      )}

      <WordSearchModal
        open={addWordModalOpen}
        onOpenChange={setAddWordModalOpen}
        deckId={id}
        deckName={deck.name}
        existingSenseIds={new Set(items.map((i) => i.senseId))}
      />
    </div>
  );
}
