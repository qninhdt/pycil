"use client";

import React, { useState } from "react";
import { Folder, Search, Loader2, Check, Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useAddSenseToDeck, useUserDecks } from "@/lib/query/content";
import type { SenseItem } from "@/lib/api/types";

interface AddToDeckModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sense: SenseItem | null;
  wordHeadword: string;
  onSuccess?: (senseId: number, nodeId: string) => void;
}

export function AddToDeckModal({
  open,
  onOpenChange,
  sense,
  wordHeadword,
  onSuccess,
}: AddToDeckModalProps) {
  const [filter, setFilter] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const { data: decks = [], isLoading: isLoadingDecks } = useUserDecks();
  const addSenseMutation = useAddSenseToDeck();

  if (!sense) return null;

  const filteredDecks = decks.filter((deck) =>
    deck.name.toLowerCase().includes(filter.toLowerCase())
  );

  const handleSave = async (nodeId: string) => {
    if (!sense.senseId) return;
    setSelectedNodeId(nodeId);
    try {
      await addSenseMutation.mutateAsync({ nodeId, senseId: sense.senseId });
      if (onSuccess) {
        onSuccess(sense.senseId, nodeId);
      }
      onOpenChange(false);
    } catch (err) {
      console.error("Failed to add sense to deck:", err);
    } finally {
      setSelectedNodeId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">Save to Deck</DialogTitle>
          <DialogDescription className="text-xs">
            Choose a target deck to save the definition for{" "}
            <span className="font-semibold text-foreground">"{wordHeadword}"</span>.
          </DialogDescription>
        </DialogHeader>

        <div className="p-3 bg-muted/40 rounded-lg border border-border/50 text-xs space-y-1">
          <div className="flex items-center gap-2 font-medium text-foreground">
            <span>{sense.definition}</span>
            {sense.pos && <Badge variant="secondary" className="text-[10px]">{sense.pos}</Badge>}
          </div>
          {sense.cefrLevel && (
            <span className="text-[10px] text-muted-foreground uppercase font-bold">
              Level {sense.cefrLevel}
            </span>
          )}
        </div>

        <div className="relative mt-2">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search your decks..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-9 text-sm"
          />
        </div>

        <ScrollArea className="h-56 pr-3 mt-1">
          {isLoadingDecks ? (
            <div className="flex items-center justify-center h-40 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
              Loading decks...
            </div>
          ) : filteredDecks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-center text-muted-foreground text-xs p-4">
              <Folder className="h-8 w-8 mb-2 opacity-40" />
              {filter ? "No matching decks found." : "No decks created yet. Create a deck in your Library first."}
            </div>
          ) : (
            <div className="space-y-1.5">
              {filteredDecks.map((deck) => {
                const isSaving = addSenseMutation.isPending && selectedNodeId === deck.id;

                return (
                  <div
                    key={deck.id}
                    className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-card hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Folder className="h-4 w-4 text-primary shrink-0" />
                      <div className="truncate">
                        <p className="text-sm font-medium truncate text-foreground">{deck.name}</p>
                        {deck.description && (
                          <p className="text-xs text-muted-foreground truncate">{deck.description}</p>
                        )}
                      </div>
                    </div>

                    <Button
                      size="sm"
                      variant="default"
                      disabled={addSenseMutation.isPending}
                      onClick={() => handleSave(deck.id)}
                      className="shrink-0 h-8 text-xs gap-1"
                    >
                      {isSaving ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <>
                          <Plus className="h-3.5 w-3.5" />
                          Save
                        </>
                      )}
                    </Button>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
