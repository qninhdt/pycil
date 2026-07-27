"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, BrainCircuit } from "lucide-react";
import Link from "next/link";
import { getFolderWeakestAction } from "@/lib/actions/stats";
import type { WeakSenseRead } from "@/lib/api/types";
import { MasteryBadge } from "@/components/decks/mastery-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

interface WeakestWordsCardProps {
  nodeId?: string;
}

export function WeakestWordsCard({ nodeId }: WeakestWordsCardProps) {
  const [weakWords, setWeakWords] = useState<WeakSenseRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        // If no specific nodeId, fetch user's global weak words or fallback
        const targetId = nodeId || "";
        if (targetId) {
          const list = await getFolderWeakestAction(targetId, 5);
          setWeakWords(list);
        }
      } catch (err) {
        console.error("Failed to load weak words:", err);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [nodeId]);

  if (!nodeId) return null;

  if (isLoading) {
    return <Skeleton className="h-44 w-full rounded-2xl" />;
  }

  if (weakWords.length === 0) return null;

  return (
    <div className="bg-amber-500/5 dark:bg-amber-500/10 border border-amber-500/20 p-5 rounded-2xl space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-bold">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <h3 className="text-base tracking-tight">Từ vựng cần cải thiện gấp</h3>
        </div>
        <Button size="sm" variant="outline" render={<Link href={`/study?deckId=${nodeId}`} />}>
          <span className="flex items-center gap-1.5 text-xs">
            <BrainCircuit className="w-3.5 h-3.5" />
            <span>Ôn ngay</span>
            <ArrowRight className="w-3 h-3" />
          </span>
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        {weakWords.map((item) => (
          <div
            key={item.senseId}
            className="p-3 rounded-xl bg-card border border-border/60 flex items-center justify-between gap-2 shadow-2xs"
          >
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground truncate">
                {item.definition || `Từ #${item.senseId}`}
              </p>
              <span className="text-[10px] text-muted-foreground font-mono">
                Sense #{item.senseId}
              </span>
            </div>
            <MasteryBadge score={item.mastery || 0} />
          </div>
        ))}
      </div>
    </div>
  );
}
