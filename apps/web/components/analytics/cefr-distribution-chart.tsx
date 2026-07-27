"use client";

import { useEffect, useState } from "react";
import { Award, BarChart2 } from "lucide-react";
import { getFolderCefrAction } from "@/lib/actions/stats";
import type { CefrDistribution } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";

interface CefrDistributionChartProps {
  nodeId: string;
}

const CEFR_COLORS: Record<string, string> = {
  A1: "bg-emerald-500 text-white",
  A2: "bg-teal-500 text-white",
  B1: "bg-blue-500 text-white",
  B2: "bg-indigo-500 text-white",
  C1: "bg-purple-500 text-white",
  C2: "bg-rose-500 text-white",
  UNKNOWN: "bg-neutral-500 text-white",
};

export function CefrDistributionChart({ nodeId }: CefrDistributionChartProps) {
  const [cefrData, setCefrData] = useState<CefrDistribution>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const data = await getFolderCefrAction(nodeId);
        setCefrData(data);
      } catch (err) {
        console.error("Failed to load CEFR data:", err);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [nodeId]);

  if (isLoading) {
    return <Skeleton className="h-32 w-full rounded-2xl" />;
  }

  const entries = Object.entries(cefrData);
  const total = entries.reduce((acc, [, count]) => acc + count, 0);

  if (total === 0) return null;

  return (
    <div className="p-5 rounded-2xl bg-card border border-border/60 space-y-3 shadow-2xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Award className="w-4 h-4 text-primary" />
          <span>Phân bổ trình độ CEFR</span>
        </div>
        <span className="text-xs text-muted-foreground font-mono">{total} từ vựng</span>
      </div>

      {/* Stacked Progress Bar */}
      <div className="h-3 w-full rounded-full overflow-hidden flex bg-neutral-100 dark:bg-neutral-800">
        {entries.map(([level, count]) => {
          const pct = ((count / total) * 100).toFixed(1);
          const colorClass = CEFR_COLORS[level.toUpperCase()] || CEFR_COLORS.UNKNOWN;
          return (
            <div
              key={level}
              style={{ width: `${pct}%` }}
              className={`h-full transition-all ${colorClass}`}
              title={`${level}: ${count} words (${pct}%)`}
            />
          );
        })}
      </div>

      {/* Legend Grid */}
      <div className="flex items-center gap-3 flex-wrap pt-1">
        {entries.map(([level, count]) => {
          const colorClass = CEFR_COLORS[level.toUpperCase()] || CEFR_COLORS.UNKNOWN;
          return (
            <div key={level} className="flex items-center gap-1.5 text-xs">
              <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-bold ${colorClass}`}>
                {level}
              </span>
              <span className="text-muted-foreground font-mono">{count}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
