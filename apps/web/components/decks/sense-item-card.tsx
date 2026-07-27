"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Trash2 } from "lucide-react";
import type { SenseItem } from "@/lib/api/types";
import { MasteryBadge } from "@/components/decks/mastery-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormattedExample } from "@/components/common/formatted-example";

interface SenseItemCardProps {
  item: SenseItem;
  onRemove: (senseId: number) => void;
  isRemoving?: boolean;
}

export function SenseItemCard({ item, onRemove, isRemoving }: SenseItemCardProps) {
  const [showExamples, setShowExamples] = useState(false);

  return (
    <Card className="hover:border-primary/40 transition-all shadow-sm">
      <CardContent className="p-5 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            {item.pos && (
              <Badge variant="secondary" className="text-xs capitalize font-medium">
                {item.pos}
              </Badge>
            )}

            {item.cefrLevel && (
              <Badge variant="outline" className="text-xs uppercase font-semibold text-primary border-primary/30">
                {item.cefrLevel}
              </Badge>
            )}

            <MasteryBadge score={item.mastery || 0} />
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => onRemove(item.senseId)}
            disabled={isRemoving}
            className="h-8 w-8 text-muted-foreground hover:text-destructive shrink-0"
            title="Remove from deck"
          >
            <Trash2 className="h-4 w-4" />
            <span className="sr-only">Remove from deck</span>
          </Button>
        </div>

        <div className="space-y-1.5">
          <p className="text-sm font-medium text-foreground leading-relaxed">
            {item.definition}
          </p>

          {item.tier && (
            <p className="text-xs text-muted-foreground">
              Tier: <span className="capitalize">{item.tier}</span>
            </p>
          )}
        </div>

        {item.examples && item.examples.length > 0 && (
          <div className="pt-2 border-t border-border/40">
            <button
              type="button"
              onClick={() => setShowExamples(!showExamples)}
              className="text-xs font-medium text-primary hover:underline flex items-center gap-1 focus:outline-none"
            >
              {showExamples ? (
                <>
                  <ChevronUp className="h-3.5 w-3.5" />
                  Hide examples ({item.examples.length})
                </>
              ) : (
                <>
                  <ChevronDown className="h-3.5 w-3.5" />
                  Show examples ({item.examples.length})
                </>
              )}
            </button>

            {showExamples && (
              <ul className="mt-2 space-y-1.5 text-xs text-muted-foreground pl-3 border-l-2 border-primary/20">
                {item.examples.map((example, idx) => (
                  <li key={idx} className="italic">
                    <FormattedExample text={example} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
