"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LearningProgressBars } from "./learning-progress-bars";
import { MultipleChoiceQuestion } from "./multiple-choice-question";
import { ReviewFooter } from "./review-footer";
import { LearningSessionLoading } from "./learning-session-loading";
import { SessionCompleteSummary } from "./session-complete";
import { useBeLearningSession } from "@/hooks/use-be-learning-session";
import {
  beQuestionToFe,
  beQuestionWithResultToFe,
} from "@/lib/adapters/be-question-to-fe";
import { cn } from "@/lib/utils";
import type { LearningProgress, Question } from "@/types/learning";

interface LearningSessionComponentProps {
  deckId: string;
  sessionSize?: number;
  onRestart?: () => void;
  onNewSession?: () => void;
  className?: string;
}

export function LearningSessionComponent({
  deckId,
  sessionSize = 25,
  onRestart,
  onNewSession,
  className,
}: LearningSessionComponentProps) {
  const session = useBeLearningSession(deckId, sessionSize);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  useEffect(() => {
    if (!session.current) setSelectedIndex(null);
  }, [session.current]);

  const currentQuestion: Question | null = useMemo(() => {
    if (session.current) {
      return beQuestionWithResultToFe(
        { id: session.current.question_id, type: "MCQ", data: session.current.data },
        session.current.selected_index,
        session.current.result.correct_index,
        session.current.result.correct
      );
    }
    if (session.question?.status === "ready" && session.question.question) {
      return beQuestionToFe(session.question.question);
    }
    return null;
  }, [session.current, session.question]);

  const showResult = !!session.current;

  const progressData = session.question ?? {
    round_index: 0,
    round_position: 0,
    round_size: 5,
  };
  const roundIndex = session.current
    ? session.current.round_index
    : progressData.round_index;
  const roundPosition = session.current
    ? session.current.round_position
    : progressData.round_position;
  const roundSize = session.current
    ? session.current.round_size
    : progressData.round_size;

  const progress: LearningProgress = {
    totalReviewedWords: session.answeredCount,
    targetWordsCount: session.selectedCount || sessionSize,
    currentRoundProgress:
      roundSize > 0 ? Math.round((roundPosition / roundSize) * 100) : 0,
    totalRoundsProgress:
      session.selectedCount > 0
        ? Math.round((session.answeredCount / session.selectedCount) * 100)
        : 0,
    currentRound: roundIndex + 1,
    totalRounds: Math.max(
      1,
      Math.ceil((session.selectedCount || sessionSize) / Math.max(roundSize, 1))
    ),
  };

  const segments = Array.from({ length: Math.max(roundSize, 1) }, (_, i) => ({
    id: `s-${roundIndex}-${i}`,
    status:
      i < roundPosition
        ? ("correct" as const)
        : i === roundPosition && session.current
          ? session.current.result.correct
            ? ("correct" as const)
            : ("incorrect" as const)
          : ("unanswered" as const),
  }));

  if (session.phase === "starting") {
    return <LearningSessionLoading className={className} />;
  }

  if (session.phase === "error") {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center space-y-3">
          <div className="text-lg font-medium">Could not start session</div>
          <p className="text-sm text-muted-foreground">
            {session.errorMessage ?? "Please try again."}
          </p>
        </div>
      </div>
    );
  }

  if (session.phase === "session_complete") {
    const durationSec = session.startedAt
      ? Math.round((Date.now() - session.startedAt) / 1000)
      : 0;
    return (
      <SessionCompleteSummary
        totalAnswered={session.answeredCount}
        correct={session.correctCount}
        durationSeconds={durationSec}
        onRestart={onRestart}
        onNewSession={onNewSession}
        className={className}
      />
    );
  }

  if (!currentQuestion) {
    return <LearningSessionLoading className={className} />;
  }

  const handleAnswer = (answer: string) => {
    if (!currentQuestion.options || showResult) return;
    const idx = currentQuestion.options.indexOf(answer);
    if (idx < 0) return;
    setSelectedIndex(idx);
    session.submit(idx);
  };

  const handleNext = () => {
    if (!showResult) return;
    setSelectedIndex(null);
    session.next();
  };

  const isLastQuestion =
    !!session.current && session.current.result.session_complete;
  const showRoundCompleteCta =
    !!session.current &&
    session.current.result.round_complete &&
    !session.current.result.session_complete;

  return (
    <div className={cn("space-y-6 pb-24", className)}>
      <div className="w-full mx-auto">
        <LearningProgressBars progress={progress} segments={segments} />
      </div>

      {showRoundCompleteCta && (
        <div className="rounded-md border bg-muted/40 p-4 text-center">
          <p className="font-medium">Round {roundIndex + 1} complete</p>
          <p className="text-sm text-muted-foreground">
            Tap continue to start the next round.
          </p>
        </div>
      )}

      <Card className="w-full mx-auto">
        <CardContent>
          <MultipleChoiceQuestion
            question={currentQuestion}
            onAnswer={handleAnswer}
            showResult={showResult}
          />
          {selectedIndex !== null && !session.current && (
            <div className="mt-4 text-center text-sm text-muted-foreground">
              Submitting…
            </div>
          )}
          {session.current?.result.explanation && (
            <div className="mt-4 rounded-md bg-muted/40 p-3 text-sm">
              <span className="font-medium">Why: </span>
              {session.current.result.explanation}
            </div>
          )}
        </CardContent>
      </Card>

      <ReviewFooter
        showResult={showResult}
        isCorrect={currentQuestion.isCorrect}
        correctAnswer={currentQuestion.correctAnswer}
        questionType={currentQuestion.type}
        onNext={handleNext}
        isLastQuestion={isLastQuestion}
      />

      {/* Suppress unused warnings without changing behavior */}
      <Button className="hidden" aria-hidden tabIndex={-1}>
        noop
      </Button>
    </div>
  );
}
