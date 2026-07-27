"use client";

import { useEffect, useState } from "react";
import { BookOpen, Layers, Award } from "lucide-react";
import { getFolderItemsAction } from "@/lib/actions/content";
import type { FolderItemRead } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface FolderVocabularyTabProps {
  folderId: string;
}

export function FolderVocabularyTab({ folderId }: FolderVocabularyTabProps) {
  const [items, setItems] = useState<FolderItemRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadItems() {
      setIsLoading(true);
      try {
        const res = await getFolderItemsAction(folderId, 0, 100);
        setItems(res);
      } catch (err) {
        console.error("Failed to load folder items:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadItems();
  }, [folderId]);

  if (isLoading) {
    return (
      <div className="space-y-3 pt-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground space-y-2">
        <BookOpen className="w-8 h-8 mx-auto text-muted-foreground/60" />
        <p className="text-sm">Chưa có từ vựng nào trong các bộ từ thuộc thư mục này.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 pt-2">
      <div className="text-xs text-muted-foreground flex items-center gap-1.5 font-medium mb-3">
        <Layers className="w-3.5 h-3.5" />
        <span>Tổng cộng {items.length} từ vựng từ tất cả bộ từ con</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((item) => (
          <div
            key={item.senseId}
            className="p-4 rounded-xl bg-card border border-border/60 hover:border-border transition-all flex items-start justify-between gap-3 shadow-2xs"
          >
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground leading-snug">
                {item.definition}
              </p>
              <div className="flex items-center gap-2 pt-1">
                <Badge variant="outline" className="text-[10px] uppercase font-mono">
                  {item.tier}
                </Badge>
                {item.cefrLevel && (
                  <Badge variant="secondary" className="text-[10px] font-bold">
                    CEFR {item.cefrLevel}
                  </Badge>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0 pt-0.5">
              <Award className="w-3.5 h-3.5 text-amber-500" />
              <span className="font-mono text-[11px]">#{item.senseId}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
