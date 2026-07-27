"use client";

import React, { useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle, ArrowRight, Award } from "lucide-react";
import type { GradeResponse } from "@/lib/api/types";

interface FeedbackBannerProps {
  result: GradeResponse;
  onNext: () => void;
}

export function FeedbackBanner({ result, onNext }: FeedbackBannerProps) {
  const isCorrect = result.isCorrect ?? false;
  const score = result.gradeScore !== undefined ? Math.round(result.gradeScore * 100) : null;
  const masteryBefore = result.masteryBefore ?? 0;
  const masteryAfter = result.masteryAfter ?? 0;
  const masteryDiff = masteryAfter - masteryBefore;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onNext();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onNext]);

  return (
    <div
      className={`p-6 rounded-2xl border-2 shadow-lg transition-all animate-in fade-in slide-in-from-bottom-4 ${
        isCorrect
          ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-950 dark:text-emerald-100"
          : "bg-rose-500/10 border-rose-500/40 text-rose-950 dark:text-rose-100"
      }`}
    >
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-3">
          <div className="flex items-center gap-3 flex-wrap">
            {isCorrect ? (
              <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white gap-1.5 text-sm py-1 px-3">
                <CheckCircle2 className="w-4 h-4" /> Chính xác!
              </Badge>
            ) : (
              <Badge className="bg-rose-500 hover:bg-rose-600 text-white gap-1.5 text-sm py-1 px-3">
                <XCircle className="w-4 h-4" /> Chưa chính xác
              </Badge>
            )}

            {score !== null && (
              <Badge variant="outline" className="text-sm py-1 px-3">
                Điểm: {score}%
              </Badge>
            )}

            {masteryDiff !== 0 && (
              <Badge
                className={`gap-1 text-sm py-1 px-3 ${
                  masteryDiff > 0
                    ? "bg-emerald-600/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/30"
                    : "bg-rose-600/20 text-rose-700 dark:text-rose-300 border-rose-500/30"
                }`}
              >
                <Award className="w-3.5 h-3.5" />
                Mastery: {masteryBefore}% → {masteryAfter}% ({masteryDiff > 0 ? `+${masteryDiff}` : masteryDiff}%)
              </Badge>
            )}

            {/* FSRS Estimated Review Intervals */}
            <div className="flex items-center gap-1.5 text-xs pt-1">
              <span className="text-muted-foreground font-medium">Dự kiến lặp lại:</span>
              {isCorrect ? (
                <>
                  <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono font-semibold">
                    Good: 3 ngày
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 font-mono font-semibold">
                    Easy: 7 ngày
                  </span>
                </>
              ) : (
                <>
                  <span className="px-2 py-0.5 rounded-md bg-rose-500/10 text-rose-600 dark:text-rose-400 font-mono font-semibold">
                    Again: 10 phút
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 font-mono font-semibold">
                    Hard: 1 ngày
                  </span>
                </>
              )}
            </div>
          </div>

          {result.gradeFeedback && (
            <p className="text-sm md:text-base leading-relaxed opacity-90 font-medium">
              {result.gradeFeedback}
            </p>
          )}
        </div>

        <Button
          onClick={onNext}
          size="lg"
          className={`shrink-0 font-bold px-8 gap-2 ${
            isCorrect
              ? "bg-emerald-600 hover:bg-emerald-700 text-white"
              : "bg-rose-600 hover:bg-rose-700 text-white"
          }`}
        >
          Câu tiếp theo <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
