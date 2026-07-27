"use client";

import { Award, BookOpen, Clock } from "lucide-react";
import type { DashboardStatsRead } from "@/lib/api/types";

interface DashboardMetricsGridProps {
  stats: DashboardStatsRead;
}

export function DashboardMetricsGrid({ stats }: DashboardMetricsGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Total Learned Words */}
      <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-sm flex items-center gap-4">
        <div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400">
          <BookOpen className="w-6 h-6" />
        </div>
        <div>
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
            Total Learned Words
          </p>
          <h3 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {stats.totalLearnedWords.toLocaleString()}
          </h3>
        </div>
      </div>

      {/* Words Due Today */}
      <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-sm flex items-center gap-4">
        <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/50 text-amber-600 dark:text-amber-400">
          <Clock className="w-6 h-6" />
        </div>
        <div>
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
            Due Today
          </p>
          <h3 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {stats.dueTodayCount.toLocaleString()}
          </h3>
        </div>
      </div>

      {/* Average Mastery % */}
      <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-sm flex items-center gap-4">
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400">
          <Award className="w-6 h-6" />
        </div>
        <div>
          <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
            Average Mastery
          </p>
          <h3 className="text-2xl font-bold text-neutral-900 dark:text-neutral-100">
            {stats.masteryPercentage.toFixed(1)}%
          </h3>
        </div>
      </div>
    </div>
  );
}
