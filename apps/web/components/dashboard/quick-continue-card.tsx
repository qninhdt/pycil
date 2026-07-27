"use client";

import Link from "next/link";
import { ArrowRight, Play, Sparkles } from "lucide-react";
import type { RecentSessionInfo } from "@/lib/api/types";

interface QuickContinueCardProps {
  recentSession: RecentSessionInfo | null;
}

export function QuickContinueCard({ recentSession }: QuickContinueCardProps) {
  if (!recentSession) {
    return (
      <div className="p-6 rounded-2xl border border-neutral-200 bg-linear-to-r from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/40 dark:border-neutral-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              Ready to start learning?
            </h3>
          </div>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            Explore your deck library or create a new vocabulary collection to get started.
          </p>
        </div>
        <Link
          href="/library"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-medium shadow-sm transition-colors text-sm shrink-0"
        >
          Go to Library
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 rounded-2xl border border-neutral-200 bg-linear-to-r from-blue-50 to-indigo-50 dark:from-blue-950/40 dark:to-indigo-950/40 dark:border-neutral-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Play className="w-5 h-5 text-blue-600 dark:text-blue-400 fill-current" />
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            Continue Learning: {recentSession.deckTitle}
          </h3>
        </div>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          You have <span className="font-semibold text-neutral-900 dark:text-neutral-100">{recentSession.remainingCount} words</span> queued for review in this deck today.
        </p>
      </div>
      <Link
        href={`/study?node_id=${recentSession.nodeId}`}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-medium shadow-sm transition-colors text-sm shrink-0"
      >
        Resume Session
        <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
}
