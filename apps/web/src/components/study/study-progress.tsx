import React, { memo, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { StudyProgressData } from "@/types";

interface StudyProgressProps {
  readonly studyProgress: StudyProgressData;
  readonly onStudySection?: (section: string) => void;
}

// --- Constants ---
const PROGRESS_SECTIONS = [
  {
    key: "newCards" as const,
    label: "New cards",
    color: "bg-destructive",
    progressColor: "[&>div]:bg-destructive",
  },
  {
    key: "stillLearning" as const,
    label: "Still learning",
    color: "bg-primary",
    progressColor: "[&>div]:bg-primary",
  },
  {
    key: "almostDone" as const,
    label: "Almost done",
    color: "bg-secondary",
    progressColor: "[&>div]:bg-secondary",
  },
  {
    key: "mastered" as const,
    label: "Mastered",
    color: "bg-accent",
    progressColor: "[&>div]:bg-accent",
  },
] as const;

/**
 * Memoized progress item component
 */
const ProgressItem = memo<{
  readonly label: string;
  readonly count: number;
  readonly color: string;
  readonly progressColor: string;
  readonly value: number;
  readonly onStudy?: () => void;
}>(({ label, count, color, progressColor, value, onStudy }) => (
  <div>
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full ${color}`} aria-hidden="true" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground">{count}</span>
        {count > 0 && (
          <Button
            size="sm"
            variant="outline"
            className="h-8"
            onClick={onStudy}
            aria-label={`Study ${count} ${label.toLowerCase()}`}
          >
            Study
          </Button>
        )}
      </div>
    </div>
    <Progress
      value={value}
      className={`h-3 ${progressColor}`}
      aria-label={`${label}: ${count} cards, ${value}% complete`}
    />
  </div>
));

ProgressItem.displayName = "ProgressItem";

/**
 * Optimized study progress component
 */
export const StudyProgress = memo<StudyProgressProps>(
  ({ studyProgress, onStudySection }) => {
    // Calculate overall progress and items
    const { overallProgress, progressItems } = useMemo(() => {
      const total = PROGRESS_SECTIONS.reduce(
        (sum, section) => sum + studyProgress[section.key],
        0
      );

      const masteredCards = studyProgress.mastered;
      const progress =
        total > 0 ? Math.round((masteredCards / total) * 100) : 0;

      const items = PROGRESS_SECTIONS.map((section) => ({
        ...section,
        count: studyProgress[section.key],
        value:
          section.key === "newCards" && studyProgress[section.key] > 0
            ? 100
            : 0,
      }));

      return {
        overallProgress: progress,
        progressItems: items,
      };
    }, [studyProgress]);

    // Memoized study handler
    const handleStudySection = useCallback(
      (sectionKey: string) => {
        onStudySection?.(sectionKey);
      },
      [onStudySection]
    );

    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Studying Progress</CardTitle>
            <span
              className="text-2xl font-bold"
              aria-label={`Overall progress: ${overallProgress}%`}
            >
              {overallProgress}%
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-3">
            {progressItems.map((item) => (
              <ProgressItem
                key={item.key}
                label={item.label}
                count={item.count}
                color={item.color}
                progressColor={item.progressColor}
                value={item.value}
                onStudy={() => handleStudySection(item.key)}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }
);

StudyProgress.displayName = "StudyProgress";
