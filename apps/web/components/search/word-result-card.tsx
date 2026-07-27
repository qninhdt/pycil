"use client";

import React from "react";
import { Plus, BookOpen, Volume2, BookmarkCheck, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SenseItem, WordSearchRead } from "@/lib/api/types";

import { FormattedExample } from "@/components/common/formatted-example";

interface WordResultCardProps {
  word: WordSearchRead;
  onSelectSense: (sense: SenseItem, wordHeadword: string) => void;
  onGenerateAi?: (query: string) => void;
  isGenerating?: boolean;
  savedSenseIds?: Set<number>;
}

export function WordResultCard({
  word,
  onSelectSense,
  onGenerateAi,
  isGenerating = false,
  savedSenseIds,
}: WordResultCardProps) {
  const senses = word.senses || [];

  return (
    <Card className="overflow-hidden border-border/60 shadow-sm transition-shadow hover:shadow-md">
      <CardHeader className="bg-muted/30 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <CardTitle className="text-2xl font-bold tracking-tight text-foreground">
              {word.display}
            </CardTitle>
            {word.pos && (
              <Badge variant="secondary" className="font-mono text-xs capitalize">
                {word.pos}
              </Badge>
            )}
            {word.entryType && (
              <Badge variant="outline" className="text-xs text-muted-foreground">
                {word.entryType}
              </Badge>
            )}
          </div>
          {word.gloss && (
            <span className="text-sm italic text-muted-foreground">
              "{word.gloss}"
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="pt-4 divide-y divide-border/40">
        {senses.length === 0 ? (
          <div className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground italic">
              Chưa có định nghĩa từ vựng chi tiết cho thẻ từ này trong từ điển.
            </p>
            {onGenerateAi && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onGenerateAi(word.display)}
                disabled={isGenerating}
                className="gap-1.5 text-xs text-primary border-primary/30 hover:bg-primary/5 shrink-0"
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>Sinh từ vựng bằng AI</span>
              </Button>
            )}
          </div>
        ) : (
          senses.map((sense, idx) => {
            const isSaved = savedSenseIds?.has(sense.senseId);
            return (
              <div key={sense.senseId || idx} className="py-3.5 first:pt-0 last:pb-0 flex flex-col gap-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-primary">
                        {idx + 1}. {sense.definition}
                      </span>
                      {sense.cefrLevel && (
                        <Badge variant="outline" className="text-[10px] font-bold uppercase bg-primary/5 text-primary border-primary/20">
                          {sense.cefrLevel}
                        </Badge>
                      )}
                      {sense.tier && (
                        <Badge variant="ghost" className="text-[10px] text-muted-foreground">
                          {sense.tier}
                        </Badge>
                      )}
                    </div>

                    {sense.examples && sense.examples.length > 0 && (
                      <ul className="pl-4 mt-1 space-y-1 list-disc text-xs text-muted-foreground">
                        {sense.examples.map((ex, exIdx) => (
                          <li key={exIdx} className="italic">
                            <FormattedExample text={ex} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <Button
                    size="sm"
                    variant={isSaved ? "secondary" : "outline"}
                    disabled={isSaved}
                    onClick={() => onSelectSense(sense, word.display)}
                    className="shrink-0 gap-1.5 h-8 text-xs font-medium"
                  >
                    {isSaved ? (
                      <>
                        <BookmarkCheck className="h-3.5 w-3.5 text-emerald-600" />
                        Saved
                      </>
                    ) : (
                      <>
                        <Plus className="h-3.5 w-3.5" />
                        Save to Deck
                      </>
                    )}
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
