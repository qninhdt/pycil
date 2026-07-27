"use client";

import React from "react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WordResultCard } from "./word-result-card";
import { EmptySearchState } from "./empty-search-state";
import type { SenseItem, WordSearchRead } from "@/lib/api/types";

interface WordResultListProps {
  query: string;
  results: WordSearchRead[];
  isLoading?: boolean;
  onSelectSense: (sense: SenseItem, wordHeadword: string) => void;
  onGenerateAi: (query: string) => void;
  isGenerating?: boolean;
  savedSenseIds?: Set<number>;
}

export function WordResultList({
  query,
  results,
  isLoading = false,
  onSelectSense,
  onGenerateAi,
  isGenerating = false,
  savedSenseIds,
}: WordResultListProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2].map((i) => (
          <div key={i} className="h-44 rounded-xl border bg-card/50 animate-pulse p-6 space-y-3">
            <div className="h-6 w-32 bg-muted rounded" />
            <div className="h-4 w-full bg-muted/60 rounded" />
            <div className="h-4 w-3/4 bg-muted/40 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <EmptySearchState
        query={query}
        onGenerateAi={onGenerateAi}
        isGenerating={isGenerating}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">
          Tìm thấy <span className="font-bold text-foreground">{results.length}</span> mục từ điển cho "{query}"
        </p>

        <Button
          variant="outline"
          size="sm"
          onClick={() => onGenerateAi(query)}
          disabled={isGenerating}
          className="gap-1.5 text-xs border-primary/30 text-primary hover:bg-primary/5 shrink-0"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Sinh nghĩa AI cho "{query}"</span>
        </Button>
      </div>

      <div className="space-y-4">
        {results.map((word, idx) => (
          <WordResultCard
            key={word.wordId || word.cambridgeId || idx}
            word={word}
            onSelectSense={onSelectSense}
            onGenerateAi={onGenerateAi}
            isGenerating={isGenerating}
            savedSenseIds={savedSenseIds}
          />
        ))}
      </div>
    </div>
  );
}
