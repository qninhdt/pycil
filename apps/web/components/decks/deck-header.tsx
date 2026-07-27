"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Layers, Plus, Play, Lock, Globe, Settings } from "lucide-react";
import type { NodeItem } from "@/lib/api/types";
import { MasteryBadge } from "@/components/decks/mastery-badge";
import { DeckSettingsDialog } from "@/components/decks/deck-settings-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface DeckHeaderProps {
  deck: NodeItem;
  totalItems: number;
  avgMastery?: number;
  onAddWordClick?: () => void;
}

export function DeckHeader({ deck, totalItems, avgMastery = 0, onAddWordClick }: DeckHeaderProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="space-y-4">
      <Link
        href={deck.parentNodeId ? `/library?folderId=${deck.parentNodeId}` : "/library"}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        <span>Back to Library</span>
      </Link>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card p-6 rounded-2xl border border-border/60 shadow-sm">
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant={deck.visibility === "PUBLIC" ? "default" : "secondary"}
              className="text-[10px] uppercase tracking-wider font-semibold"
            >
              {deck.visibility === "PUBLIC" ? (
                <span className="flex items-center gap-1">
                  <Globe className="h-3 w-3" /> Public Deck
                </span>
              ) : (
                <span className="flex items-center gap-1">
                  <Lock className="h-3 w-3" /> Private Deck
                </span>
              )}
            </Badge>
            <span className="text-xs text-muted-foreground">• {totalItems} items</span>
          </div>

          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Layers className="h-8 w-8 text-primary shrink-0" />
            <span>{deck.name}</span>
          </h1>

          {deck.description && (
            <p className="text-sm text-muted-foreground leading-relaxed">
              {deck.description}
            </p>
          )}

          <div className="pt-2 flex items-center gap-3">
            <span className="text-xs font-medium text-muted-foreground">Overall Mastery:</span>
            <MasteryBadge score={avgMastery} />
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0 pt-2 md:pt-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSettingsOpen(true)}
            title="Cài đặt bộ từ"
            className="rounded-xl"
          >
            <Settings className="h-4 w-4 text-muted-foreground hover:text-foreground" />
          </Button>

          <Button variant="outline" onClick={onAddWordClick}>
            <span className="flex items-center gap-2">
              <Plus className="h-4 w-4 text-primary" />
              <span>Thêm từ mới</span>
            </span>
          </Button>

          <Button render={<Link href={`/study?deckId=${deck.id}`} />}>
            <span className="flex items-center gap-2">
              <Play className="h-4 w-4 fill-primary-foreground" />
              <span>Học ngay</span>
            </span>
          </Button>
        </div>
      </div>

      <DeckSettingsDialog
        nodeId={deck.id}
        deckName={deck.name}
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
      />
    </div>
  );
}
