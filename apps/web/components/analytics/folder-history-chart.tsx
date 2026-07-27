"use client";

import { useEffect, useState } from "react";
import { TrendingUp, Calendar } from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { getFolderHistoryAction } from "@/lib/actions/stats";
import type { HistoryBucketRead } from "@/lib/api/types";
import { Skeleton } from "@/components/ui/skeleton";

interface FolderHistoryChartProps {
  nodeId: string;
}

export function FolderHistoryChart({ nodeId }: FolderHistoryChartProps) {
  const [history, setHistory] = useState<HistoryBucketRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const data = await getFolderHistoryAction(nodeId);
        setHistory(data);
      } catch (err) {
        console.error("Failed to load folder history:", err);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [nodeId]);

  if (isLoading) {
    return <Skeleton className="h-56 w-full rounded-2xl" />;
  }

  if (history.length === 0) return null;

  return (
    <div className="p-5 rounded-2xl bg-card border border-border/60 space-y-4 shadow-2xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <TrendingUp className="w-4 h-4 text-primary" />
          <span>Lịch sử ôn tập & Tiến độ Mastery 30 ngày</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground font-mono">
          <Calendar className="w-3.5 h-3.5" />
          <span>30 ngày qua</span>
        </div>
      </div>

      <div className="h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={history} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="reviewedColor" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="masteryColor" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
            <XAxis
              dataKey="bucket"
              tickFormatter={(str: string) => {
                const date = new Date(str);
                return `${date.getMonth() + 1}/${date.getDate()}`;
              }}
              tick={{ fontSize: 10 }}
              stroke="#888888"
            />
            <YAxis tick={{ fontSize: 10 }} stroke="#888888" />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255, 255, 255, 0.95)",
                borderRadius: "12px",
                fontSize: "12px",
                border: "1px solid #e5e7eb",
              }}
            />
            <Area
              type="monotone"
              dataKey="reviewed"
              name="Từ đã ôn"
              stroke="#3b82f6"
              fillOpacity={1}
              fill="url(#reviewedColor)"
            />
            <Area
              type="monotone"
              dataKey="avgMastery"
              name="Mastery TB %"
              stroke="#10b981"
              fillOpacity={1}
              fill="url(#masteryColor)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
