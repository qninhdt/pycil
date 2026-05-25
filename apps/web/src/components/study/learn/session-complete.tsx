"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Trophy, Clock, Target, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionCompleteSummaryProps {
  totalAnswered: number;
  correct: number;
  durationSeconds: number;
  onRestart?: () => void;
  onNewSession?: () => void;
  className?: string;
}

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.max(0, totalSeconds - m * 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

export function SessionCompleteSummary({
  totalAnswered,
  correct,
  durationSeconds,
  onRestart,
  onNewSession,
  className,
}: SessionCompleteSummaryProps) {
  const accuracy = totalAnswered === 0
    ? 0
    : Math.round((correct / totalAnswered) * 100);

  const performanceColor =
    accuracy >= 90
      ? "text-green-600 dark:text-green-400"
      : accuracy >= 70
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-red-600 dark:text-red-400";

  const performanceMessage =
    accuracy >= 90
      ? "Excellent work!"
      : accuracy >= 70
        ? "Good job!"
        : "Keep practicing!";

  return (
    <Card className={cn("w-full mx-auto max-w-md", className)}>
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          <div className="p-4 rounded-full bg-primary/10">
            <Trophy className="h-12 w-12 text-primary" />
          </div>
        </div>
        <CardTitle className="text-2xl">Session Complete</CardTitle>
        <p className="text-muted-foreground">{performanceMessage}</p>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center space-y-1">
            <div className="flex items-center justify-center gap-1">
              <Target className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Accuracy</span>
            </div>
            <div className={cn("text-2xl font-bold", performanceColor)}>
              {accuracy}%
            </div>
          </div>

          <div className="text-center space-y-1">
            <div className="flex items-center justify-center gap-1">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Time</span>
            </div>
            <div className="text-2xl font-bold">
              {formatDuration(durationSeconds)}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Answered</span>
            <Badge variant="secondary">{totalAnswered}</Badge>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Correct</span>
            <Badge variant="default">{correct}</Badge>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Incorrect</span>
            <Badge variant="outline">{totalAnswered - correct}</Badge>
          </div>
        </div>

        <div className="flex flex-col gap-2 pt-4">
          {onRestart && (
            <Button onClick={onRestart} className="w-full">
              <Zap className="h-4 w-4 mr-2" />
              Practice Again
            </Button>
          )}
          {onNewSession && (
            <Button onClick={onNewSession} variant="outline" className="w-full">
              Start New Session
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
