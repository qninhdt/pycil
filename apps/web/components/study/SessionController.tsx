"use client";

import React, { useState, useEffect, useCallback } from "react";
import type {
  ReadyQuestion,
  GradeResponse,
  NextQuestionResponse,
} from "@/lib/api/types";
import {
  getNextQuestionAction,
  submitAnswerAction,
} from "@/lib/actions/study";
import { useTaskSnapshot } from "@/lib/realtime/use-task-snapshot";
import { QuestionPlayer } from "./QuestionPlayer";
import { SessionSummary } from "./SessionSummary";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Sparkles, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface SessionControllerProps {
  sessionId: string;
}

type SessionStatus =
  | "INITIALIZING"
  | "FETCHING_QUESTION"
  | "PENDING_GENERATION"
  | "READY"
  | "SUBMITTING"
  | "GRADING_PENDING"
  | "EXHAUSTED"
  | "ERROR";

export function SessionController({ sessionId }: SessionControllerProps) {
  const [status, setStatus] = useState<SessionStatus>("INITIALIZING");
  const [question, setQuestion] = useState<ReadyQuestion | null>(null);
  const [gradeResult, setGradeResult] = useState<GradeResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [questionTaskId, setQuestionTaskId] = useState<string | null>(null);
  const [gradingTask, setGradingTask] = useState<{ taskId: string; responseId: string; senseId: number } | null>(null);
  const questionSnapshot = useTaskSnapshot(questionTaskId);
  const gradingSnapshot = useTaskSnapshot(gradingTask?.taskId ?? null);

  // Stats tracking
  const [currentIndex, setCurrentIndex] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [correctCount, setCorrectCount] = useState(0);
  const [masteredCount, setMasteredCount] = useState(0);

  // Fetch next question logic
  const fetchNextQuestion = useCallback(async () => {
    setStatus("FETCHING_QUESTION");
    setErrorMessage(null);
    try {
      const res: NextQuestionResponse = await getNextQuestionAction(sessionId);

      if (res.state === "pending") {
        setQuestionTaskId(res.taskId);
        setStatus("PENDING_GENERATION");
      } else if (res.state === "exhausted") {
        setQuestionTaskId(null);
        setStatus("EXHAUSTED");
      } else if (res.state === "ready") {
        setQuestionTaskId(null);
        setQuestion(res);
        setGradeResult(null);
        setStatus("READY");
      }
    } catch (err) {
      console.error("Failed to fetch next question:", err);
      setErrorMessage("Không thể tải câu hỏi tiếp theo.");
      setStatus("ERROR");
    }
  }, [sessionId]);

  // Initial load
  useEffect(() => {
    fetchNextQuestion();
  }, [fetchNextQuestion]);

  useEffect(() => {
    if (questionSnapshot?.status === "succeeded") {
      fetchNextQuestion();
    }
    if (questionSnapshot?.status === "failed" || questionSnapshot?.status === "expired") {
      setErrorMessage("Không thể tạo câu hỏi tiếp theo.");
      setStatus("ERROR");
    }
  }, [fetchNextQuestion, questionSnapshot]);

  useEffect(() => {
    if (!gradingTask || !gradingSnapshot) return;
    if (gradingSnapshot.status === "succeeded") {
      const result = gradingSnapshot.result ?? {};
      const grade: GradeResponse = {
        responseId: gradingTask.responseId,
        gradeStatus: "graded",
        senseId: gradingTask.senseId,
        isCorrect: typeof result.isCorrect === "boolean" ? result.isCorrect : undefined,
        gradeScore: typeof result.gradeScore === "number" ? result.gradeScore : undefined,
        gradeFeedback: typeof result.gradeFeedback === "string" ? result.gradeFeedback : undefined,
        masteryBefore: typeof result.masteryBefore === "number" ? result.masteryBefore : undefined,
        masteryAfter: typeof result.masteryAfter === "number" ? result.masteryAfter : undefined,
      };
      setGradeResult(grade);
      if (grade.isCorrect) setCorrectCount((prev) => prev + 1);
      if (grade.masteryAfter !== undefined && grade.masteryAfter >= 80) {
        setMasteredCount((prev) => prev + 1);
      }
      setCompletedCount((prev) => prev + 1);
      setGradingTask(null);
      setStatus("READY");
    }
    if (gradingSnapshot.status === "failed" || gradingSnapshot.status === "expired") {
      setErrorMessage("Không thể chấm câu trả lời. Vui lòng thử lại.");
      setGradingTask(null);
      setStatus("READY");
    }
  }, [gradingSnapshot, gradingTask]);

  // Submit answer
  const handleSubmitAnswer = async (answerText: string) => {
    if (!question) return;
    setStatus("SUBMITTING");
    try {
      const res = await submitAnswerAction(sessionId, question.questionId, answerText);

      if (res.gradeStatus === "pending") {
        if (!res.taskId) throw new Error("missing_async_task_id");
        setStatus("GRADING_PENDING");
        setGradingTask({ taskId: res.taskId, responseId: res.responseId, senseId: res.senseId });
      } else {
        setGradeResult(res);
        if (res.isCorrect) {
          setCorrectCount((prev) => prev + 1);
        }
        if (res.masteryAfter !== undefined && res.masteryAfter >= 80) {
          setMasteredCount((prev) => prev + 1);
        }
        setCompletedCount((prev) => prev + 1);
        setStatus("READY");
      }
    } catch (err) {
      console.error("Failed to submit answer:", err);
      setErrorMessage("Không thể nộp câu trả lời. Vui lòng thử lại.");
      setStatus("READY");
    }
  };

  // Move to next question
  const handleNextQuestion = () => {
    setCurrentIndex((prev) => prev + 1);
    fetchNextQuestion();
  };

  if (status === "INITIALIZING" || status === "FETCHING_QUESTION") {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-4 max-w-md mx-auto">
        <Spinner className="w-8 h-8 text-primary" />
        <p className="text-sm font-medium text-muted-foreground animate-pulse">
          Đang chuẩn bị câu hỏi tiếp theo...
        </p>
      </div>
    );
  }

  if (status === "PENDING_GENERATION") {
    return (
      <Card className="max-w-lg mx-auto border-2 border-primary/20 shadow-md">
        <CardContent className="p-8 flex flex-col items-center text-center space-y-4">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 dark:text-amber-400">
            <Sparkles className="w-7 h-7 animate-spin" />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-foreground">AI đang tạo câu hỏi mới</h3>
            <p className="text-xs text-muted-foreground">
              Hệ thống đang chủ động tạo câu hỏi trắc nghiệm/ngữ cảnh phù hợp nhất với trình độ của bạn...
            </p>
          </div>
          <Spinner className="w-5 h-5 text-primary" />
        </CardContent>
      </Card>
    );
  }

  if (status === "EXHAUSTED") {
    return (
      <SessionSummary
        completedCount={completedCount}
        correctCount={correctCount}
        masteredCount={masteredCount}
      />
    );
  }

  if (status === "ERROR") {
    return (
      <Card className="max-w-md mx-auto border-2 border-rose-500/30">
        <CardContent className="p-8 flex flex-col items-center text-center space-y-4">
          <AlertCircle className="w-10 h-10 text-rose-500" />
          <p className="text-sm font-medium text-foreground">{errorMessage || "Đã xảy ra lỗi."}</p>
          <Button onClick={() => fetchNextQuestion()} variant="default">
            Thử lại
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!question) return null;

  return (
    <QuestionPlayer
      question={question}
      onSubmitAnswer={handleSubmitAnswer}
      onNextQuestion={handleNextQuestion}
      isSubmitting={status === "SUBMITTING"}
      isGrading={status === "GRADING_PENDING"}
      gradeResult={gradeResult}
      currentIndex={currentIndex}
    />
  );
}
