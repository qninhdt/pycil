"use client";

import React, { useEffect, useState } from "react";
import type { NodeItem, FolderStats } from "@/lib/api/types";
import { DeckStudyCard } from "./DeckStudyCard";
import { getFolderStatsAction } from "@/lib/actions/study";
import { BookOpen, FolderPlus } from "lucide-react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";

interface StudyDeckGridProps {
  initialDecks: NodeItem[];
}

export function StudyDeckGrid({ initialDecks }: StudyDeckGridProps) {
  const [statsMap, setStatsMap] = useState<Record<string, FolderStats>>({});

  useEffect(() => {
    // Fetch stats for all decks in parallel
    const fetchAllStats = async () => {
      const results: Record<string, FolderStats> = {};
      await Promise.all(
        initialDecks.map(async (deck) => {
          const stats = await getFolderStatsAction(deck.id);
          if (stats) {
            results[deck.id] = stats;
          }
        })
      );
      setStatsMap(results);
    };

    if (initialDecks.length > 0) {
      fetchAllStats();
    }
  }, [initialDecks]);

  if (initialDecks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center border-2 border-dashed rounded-2xl bg-muted/20 my-6 space-y-4">
        <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary">
          <BookOpen className="w-8 h-8" />
        </div>
        <div className="space-y-1 max-w-sm">
          <h3 className="text-lg font-bold text-foreground">Chưa có bộ từ vựng nào</h3>
          <p className="text-sm text-muted-foreground">
            Hãy tạo bộ từ (Deck) mới hoặc tìm kiếm từ vựng để bắt đầu học với thuật toán FSRS 4.5.
          </p>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <Link
            href="/library"
            className={buttonVariants({
              variant: "default",
              className: "gap-2",
            })}
          >
            <FolderPlus className="w-4 h-4" /> Quản lý thư viện
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {initialDecks.map((deck) => (
        <DeckStudyCard key={deck.id} deck={deck} stats={statsMap[deck.id]} />
      ))}
    </div>
  );
}
