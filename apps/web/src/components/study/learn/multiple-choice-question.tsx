"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { Check, X } from "lucide-react";
import type { Question } from "@/types/learning";

interface MultipleChoiceQuestionProps {
  question: Question;
  onAnswer: (answer: string) => void;
  showResult?: boolean;
  className?: string;
}

export function MultipleChoiceQuestion({
  question,
  onAnswer,
  showResult = false,
  className,
}: MultipleChoiceQuestionProps) {
  const handleOptionSelect = (option: string) => {
    if (showResult) return; // Prevent changing answer after result is shown

    // Auto-submit when option is selected
    onAnswer(option);
  };

  const getOptionStyle = (option: string) => {
    if (!showResult) {
      return "border-border hover:border-primary/50 hover:bg-accent";
    }

    // Show results
    if (option === question.correctAnswer) {
      return "border-primary bg-primary/10 text-primary";
    }

    if (option === question.userAnswer && option !== question.correctAnswer) {
      return "border-destructive bg-destructive/10 text-destructive";
    }

    return "border-border text-muted-foreground";
  };

  const getOptionIcon = (option: string, index: number) => {
    if (!showResult) {
      return (
        <div className="w-6 h-6 flex items-center justify-center mr-3">
          <span className="text-sm font-medium opacity-70">{index + 1}</span>
        </div>
      );
    }

    // Show results
    if (option === question.correctAnswer) {
      return (
        <div className="w-6 h-6 flex items-center justify-center mr-3">
          <Check className="w-4 h-4 text-primary" />
        </div>
      );
    }

    if (option === question.userAnswer && option !== question.correctAnswer) {
      return (
        <div className="w-6 h-6 flex items-center justify-center mr-3">
          <X className="w-4 h-4 text-destructive" />
        </div>
      );
    }

    return (
      <div className="w-6 h-6 flex items-center justify-center mr-3">
        <span className="text-sm font-medium opacity-70">{index + 1}</span>
      </div>
    );
  };

  return (
    <div className={cn("space-y-6", className)}>
      <div className="text-center">
        <div className="text-2xl font-bold text-foreground bg-accent/50 rounded-lg px-6 py-4">
          {question.term}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {question.options?.map((option, index) => (
          <button
            key={index}
            onClick={() => handleOptionSelect(option)}
            disabled={showResult}
            className={cn(
              "w-full text-left p-4 rounded-lg border-2 transition-all duration-200",
              "focus:outline-none focus:ring-2 focus:ring-primary/20",
              "disabled:cursor-not-allowed flex items-center",
              getOptionStyle(option)
            )}
          >
            {getOptionIcon(option, index)}
            <span className="flex-1">{option}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
