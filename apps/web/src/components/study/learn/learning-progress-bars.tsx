"use client";

import React, { memo } from "react";
import { cn } from "@/lib/utils";
import type { LearningProgress } from "@/types/learning";

interface ProgressSegment {
  id: string;
  status: "unanswered" | "correct" | "incorrect" | "skipped";
}

interface LearningProgressBarsProps {
  progress: LearningProgress;
  segments: ProgressSegment[];
  className?: string;
}

/**
 * Individual progress segment component
 */
const ProgressSegment = memo<{
  status: ProgressSegment["status"];
  className?: string;
}>(({ status, className }) => {
  const segmentClasses = cn("h-2 flex-1 overflow-hidden bg-muted", className);

  const fillClasses = cn("h-full transition-[width] duration-300", {
    "bg-transparent": status === "unanswered",
    "bg-primary": status === "correct",
    "bg-primary bg-striped": status === "incorrect" || status === "skipped",
  });

  const fillWidth = status === "unanswered" ? "0%" : "100%";

  return (
    <div className={segmentClasses} aria-label={`Question ${status}`}>
      <div className={fillClasses} style={{ width: fillWidth }} />
    </div>
  );
});

ProgressSegment.displayName = "ProgressSegment";

/**
 * Learning progress bars component showing round progress and overall progress
 */
export const LearningProgressBars = memo<LearningProgressBarsProps>(
  ({ progress, segments, className }) => {
    const answeredQuestions = segments.filter(
      (s) => s.status !== "unanswered"
    ).length;
    const totalQuestions = segments.length;

    return (
      <div className={cn("space-y-3", className)}>
        {/* Progress Bars - Inline Layout */}
        <div className="flex items-center gap-4">
          {/* Overall Progress - Single Bar */}
          <div className="flex-1 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Overall</span>
              <span className="font-medium text-muted-foreground">
                {progress.totalReviewedWords} / {progress.targetWordsCount}
              </span>
            </div>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress.totalRoundsProgress}%` }}
                aria-label={`Overall progress: ${progress.totalReviewedWords} of ${progress.targetWordsCount} words`}
              />
            </div>
          </div>

          {/* Round Progress - Segmented Bar */}
          <div className="flex-1 space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Round {progress.currentRound}
              </span>
              <span className="font-medium text-muted-foreground">
                {answeredQuestions} / {totalQuestions}
              </span>
            </div>
            <div className="flex">
              {segments.map((segment) => (
                <ProgressSegment
                  key={segment.id}
                  status={segment.status}
                  className="first:rounded-l-full last:rounded-r-full"
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }
);

LearningProgressBars.displayName = "LearningProgressBars";
