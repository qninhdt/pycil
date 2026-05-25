"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ReviewFooterProps {
  showResult: boolean;
  isCorrect?: boolean;
  correctAnswer?: string;
  userAnswer?: string;
  questionType: "multiple-choice" | "write";
  onNext: () => void;
  isLastQuestion?: boolean;
  className?: string;
}

export function ReviewFooter({
  showResult,
  isCorrect,
  correctAnswer,
  questionType,
  onNext,
  isLastQuestion = false,
  className,
}: ReviewFooterProps) {
  if (!showResult) return null;

  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 bg-background/95 backdrop-blur-sm border-t",
        "py-3 px-3 sm:py-4 sm:px-4 shadow-lg z-50",
        className
      )}
      role="region"
      aria-label="Review result and continue"
    >
      <div className="mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 max-w-4xl">
        <div className="flex-1">
          {isCorrect === true ? (
            <div className="text-primary font-medium">✓ Correct</div>
          ) : isCorrect === false ? (
            <div className="space-y-1">
              <div className="text-destructive font-medium">✗ Not quite</div>
              {questionType === "write" && correctAnswer && (
                <div className="text-sm text-muted-foreground">
                  Correct answer:{" "}
                  <span className="font-medium text-foreground">
                    {correctAnswer}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-muted-foreground">Skipped</div>
          )}
        </div>

        <div className="w-full sm:w-auto">
          <Button
            onClick={onNext}
            size="lg"
            className="w-full sm:w-auto px-6 sm:px-8"
          >
            {isLastQuestion ? "Complete Session" : "Continue"}
          </Button>
        </div>
      </div>
    </div>
  );
}
