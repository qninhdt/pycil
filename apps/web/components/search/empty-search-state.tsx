"use client";

import React from "react";
import { Sparkles, Search, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface EmptySearchStateProps {
  query: string;
  onGenerateAi: (query: string) => void;
  isGenerating?: boolean;
}

export function EmptySearchState({ query, onGenerateAi, isGenerating = false }: EmptySearchStateProps) {
  if (!query.trim()) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed rounded-xl bg-muted/20">
        <div className="p-3 rounded-full bg-primary/10 text-primary mb-3">
          <Search className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-semibold text-foreground">Type to search words</h3>
        <p className="mt-1 text-sm text-muted-foreground max-w-sm">
          Enter an English word above to search Cambridge dictionary entries or create new AI-generated definitions.
        </p>
      </div>
    );
  }

  return (
    <Card className="border-primary/20 bg-gradient-to-b from-primary/5 via-background to-background">
      <CardContent className="flex flex-col items-center justify-center p-8 text-center gap-4">
        <div className="p-3 rounded-full bg-primary/10 text-primary">
          <Sparkles className="h-8 w-8 text-primary animate-pulse" />
        </div>
        <div className="space-y-1">
          <h3 className="text-xl font-bold tracking-tight text-foreground">
            No exact dictionary match for "{query}"
          </h3>
          <p className="text-sm text-muted-foreground max-w-md">
            The word isn't listed in our standard dictionary. You can generate custom definitions, parts of speech, and example sentences using AI.
          </p>
        </div>

        <Button
          size="lg"
          onClick={() => onGenerateAi(query)}
          disabled={isGenerating}
          className="mt-2 gap-2 shadow-md hover:shadow-lg transition-all"
        >
          {isGenerating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting AI Generation...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4 fill-primary-foreground" />
              Generate "{query}" with AI
            </>
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
