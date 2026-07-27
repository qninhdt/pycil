"use client";

import React, { useState } from "react";
import type { ReadyQuestion, GradeResponse } from "@/lib/api/types";
import { DefinitionMcqCard } from "./DefinitionMcqCard";
import { ContextualMcqCard } from "./ContextualMcqCard";
import { ClozeCard } from "./ClozeCard";
import { UseInSentenceCard } from "./UseInSentenceCard";
import { FeedbackBanner } from "./FeedbackBanner";
import { Progress } from "@/components/ui/progress";

interface QuestionPlayerProps {
  question: ReadyQuestion;
  onSubmitAnswer: (answer: string) => void;
  onNextQuestion: () => void;
  isSubmitting: boolean;
  isGrading: boolean;
  gradeResult: GradeResponse | null;
  currentIndex: number;
  totalQueueSize?: number;
}

export function QuestionPlayer({
  question,
  onSubmitAnswer,
  onNextQuestion,
  isSubmitting,
  isGrading,
  gradeResult,
  currentIndex,
  totalQueueSize = 20,
}: QuestionPlayerProps) {
  const [selectedMcqOption, setSelectedMcqOption] = useState<string | null>(null);
  const [textInput, setTextInput] = useState<string>("");

  const handleSubmit = () => {
    if (question.format === "definition_mcq" || question.format === "contextual_mcq") {
      if (selectedMcqOption !== null) {
        onSubmitAnswer(selectedMcqOption);
      }
    } else {
      if (textInput.trim()) {
        onSubmitAnswer(textInput.trim());
      }
    }
  };

  const handleNext = () => {
    setSelectedMcqOption(null);
    setTextInput("");
    onNextQuestion();
  };

  const progressPercent = Math.min(
    100,
    Math.round((currentIndex / Math.max(1, totalQueueSize)) * 100)
  );

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>Tiến độ phiên học</span>
          <span>
            {currentIndex} / {totalQueueSize} thẻ
          </span>
        </div>
        <Progress value={progressPercent} className="h-2.5 rounded-full" />
      </div>

      {/* Active Question Card */}
      {!gradeResult && (
        <>
          {question.format === "definition_mcq" && (
            <DefinitionMcqCard
              stem={question.payload.stem}
              options={question.payload.options}
              selectedIndex={selectedMcqOption}
              onSelectOption={setSelectedMcqOption}
              onSubmit={handleSubmit}
              disabled={isSubmitting}
            />
          )}

          {question.format === "contextual_mcq" && (
            <ContextualMcqCard
              stem={question.payload.stem}
              options={question.payload.options}
              selectedIndex={selectedMcqOption}
              onSelectOption={setSelectedMcqOption}
              onSubmit={handleSubmit}
              disabled={isSubmitting}
            />
          )}

          {question.format === "cloze" && (
            <ClozeCard
              stemWithBlank={question.payload.stemWithBlank}
              value={textInput}
              onChange={setTextInput}
              onSubmit={handleSubmit}
              disabled={isSubmitting}
            />
          )}

          {question.format === "use_in_sentence" && (
            <UseInSentenceCard
              prompt={question.payload.prompt}
              value={textInput}
              onChange={setTextInput}
              onSubmit={handleSubmit}
              disabled={isSubmitting}
              isGrading={isGrading}
            />
          )}
        </>
      )}

      {/* Feedback Banner */}
      {gradeResult && <FeedbackBanner result={gradeResult} onNext={handleNext} />}
    </div>
  );
}
