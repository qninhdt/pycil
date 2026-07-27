"use client";

import React, { useState } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SearchBar } from "@/components/search/search-bar";
import { WordResultList } from "@/components/search/word-result-list";
import { AiGenerationBanner } from "@/components/search/ai-generation-banner";
import { useAddSenseToDeck, useSubmitWordGeneration, useWordSearch } from "@/lib/query/content";
import type { SenseItem } from "@/lib/api/types";

interface WordSearchModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deckId: string;
  deckName: string;
  existingSenseIds?: Set<number>;
}

export function WordSearchModal({
  open,
  onOpenChange,
  deckId,
  deckName,
  existingSenseIds = new Set(),
}: WordSearchModalProps) {
  const [query, setQuery] = useState("");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [activeTaskQuery, setActiveTaskQuery] = useState("");
  const [savedSenseIds, setSavedSenseIds] = useState<Set<number>>(existingSenseIds);

  const { data: searchResults = [], isLoading, refetch } = useWordSearch(query);
  const submitAiGeneration = useSubmitWordGeneration();
  const addSenseMutation = useAddSenseToDeck();

  const handleGenerateAi = async (targetQuery: string) => {
    if (!targetQuery.trim()) return;
    try {
      const res = await submitAiGeneration.mutateAsync(targetQuery.trim());
      setActiveTaskId(res.taskId);
      setActiveTaskQuery(targetQuery.trim());
      toast.info(`Đã gửi yêu cầu AI sinh từ vựng cho "${targetQuery.trim()}"`);
    } catch (err: unknown) {
      console.error("AI generation submit error:", err);
      const errMsg = err instanceof Error ? err.message : "Không thể bắt đầu sinh từ vựng";
      toast.error(errMsg);
    }
  };

  const handleSelectSense = async (sense: SenseItem, wordHeadword: string) => {
    if (!sense.senseId) return;
    try {
      await addSenseMutation.mutateAsync({ nodeId: deckId, senseId: sense.senseId });
      setSavedSenseIds((prev) => new Set(prev).add(sense.senseId!));
      toast.success(`Đã thêm từ/nghĩa "${wordHeadword}" vào bộ từ "${deckName}"!`);
    } catch (err) {
      console.error("Failed to add sense to deck:", err);
      toast.error("Không thể thêm từ vựng vào bộ từ");
    }
  };

  const handleTaskCompleted = () => {
    toast.success(`AI đã sinh xong dữ liệu từ vựng cho "${activeTaskQuery}"!`);
    refetch();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] flex flex-col p-6 gap-4">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">Thêm từ vựng mới</DialogTitle>
          <DialogDescription className="text-sm">
            Tra cứu hoặc dùng AI sinh nghĩa để thêm trực tiếp vào bộ từ vựng{" "}
            <span className="font-semibold text-foreground">"{deckName}"</span>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <SearchBar value={query} onChange={setQuery} isLoading={isLoading} />

          {activeTaskId && (
            <AiGenerationBanner
              taskId={activeTaskId}
              query={activeTaskQuery}
              onCompleted={handleTaskCompleted}
              onDismiss={() => setActiveTaskId(null)}
            />
          )}
        </div>

        <ScrollArea className="flex-1 max-h-[55vh] pr-3">
          <WordResultList
            query={query}
            results={searchResults}
            isLoading={isLoading}
            onSelectSense={handleSelectSense}
            onGenerateAi={handleGenerateAi}
            isGenerating={submitAiGeneration.isPending}
            savedSenseIds={savedSenseIds}
          />
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
