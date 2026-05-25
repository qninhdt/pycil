"use client";

/**
 * QuestionRenderer.
 *
 * Dispatches the persisted question payload to the right card component by
 * `type`. v1 only handles MULTIPLE_CHOICE; v0.2 will add WRITE / FILL.
 */
import type { QuestionRead } from "@/lib/types";

import { MultipleChoiceCard } from "@/components/multiple-choice-card";
import { checkAnswerAction } from "@/lib/question-actions";

interface QuestionRendererProps {
  question: QuestionRead;
  onResult?: (correct: boolean) => void;
}

export function QuestionRenderer({ question, onResult }: QuestionRendererProps) {
  if (question.type === "MULTIPLE_CHOICE") {
    return (
      <MultipleChoiceCard
        questionId={question.id}
        data={question.data}
        onCheck={checkAnswerAction}
        onResult={onResult}
      />
    );
  }
  return (
    <div className="rounded border border-yellow-300 bg-yellow-50 p-4 text-sm">
      Question type {question.type} is not supported in v1.
    </div>
  );
}
