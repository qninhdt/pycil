"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useStartSession,
  useSessionQuestion,
  useSubmitAnswer,
} from "@/lib/api-hooks/use-learning";
import { queryKeys } from "@/lib/api-client/query-keys";
import type {
  MCQDataPublic,
  SessionQuestionResponse,
  SubmitAnswerResponse,
  UUID,
} from "@/types/domain";

export type BeSessionPhase =
  | "starting"
  | "loading_question"
  | "ready"
  | "answered"
  | "round_complete"
  | "session_complete"
  | "error";

interface BeAnsweredQuestion {
  question_id: UUID;
  data: MCQDataPublic;
  selected_index: number;
  result: SubmitAnswerResponse;
  round_index: number;
  round_position: number;
  round_size: number;
}

export interface BeLearningSession {
  phase: BeSessionPhase;
  sessionId: string | null;
  selectedCount: number;
  question: SessionQuestionResponse | null;
  current: BeAnsweredQuestion | null;
  answeredCount: number;
  correctCount: number;
  startedAt: number | null;
  errorMessage: string | null;
  submit: (selectedIndex: number) => void;
  next: () => void;
}

export function useBeLearningSession(
  deckId: UUID,
  sessionSize = 25,
  themeId: string | null = null
): BeLearningSession {
  const qc = useQueryClient();
  const startSession = useStartSession(deckId);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedCount, setSelectedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [current, setCurrent] = useState<BeAnsweredQuestion | null>(null);
  const [answeredCount, setAnsweredCount] = useState(0);
  const [correctCount, setCorrectCount] = useState(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    startSession.mutate(
      { session_size: sessionSize, theme_id: themeId },
      {
        onSuccess: (resp) => {
          setSessionId(resp.session_id);
          setSelectedCount(resp.selected_count);
          setStartedAt(Date.now());
        },
        onError: (err: unknown) => {
          const code =
            (err as { code?: string } | null)?.code ?? "session_failed";
          setErrorMessage(code);
        },
      }
    );
  }, [sessionSize, startSession]);

  const questionQuery = useSessionQuestion(sessionId);
  const submitAnswer = useSubmitAnswer(sessionId ?? "");

  const phase: BeSessionPhase = (() => {
    if (errorMessage) return "error";
    if (!sessionId) return "starting";
    if (current) {
      if (current.result.session_complete) return "session_complete";
      if (current.result.round_complete) return "round_complete";
      return "answered";
    }
    if (questionQuery.data?.status === "session_complete")
      return "session_complete";
    if (questionQuery.data?.status === "ready" && questionQuery.data.question)
      return "ready";
    return "loading_question";
  })();

  const submit = (selectedIndex: number) => {
    if (!sessionId) return;
    const data = questionQuery.data;
    if (!data || data.status !== "ready" || !data.question) return;
    submitAnswer.mutate(
      { question_id: data.question.id, selected_index: selectedIndex },
      {
        onSuccess: (result) => {
          setCurrent({
            question_id: data.question!.id,
            data: data.question!.data as MCQDataPublic,
            selected_index: selectedIndex,
            result,
            round_index: data.round_index,
            round_position: data.round_position,
            round_size: data.round_size,
          });
          setAnsweredCount((n) => n + 1);
          if (result.correct) setCorrectCount((n) => n + 1);
        },
        onError: (err: unknown) => {
          const code = (err as { code?: string } | null)?.code ?? "submit_failed";
          setErrorMessage(code);
        },
      }
    );
  };

  const next = () => {
    if (!sessionId) return;
    setCurrent(null);
    qc.invalidateQueries({ queryKey: queryKeys.session.question(sessionId) });
  };

  return {
    phase,
    sessionId,
    selectedCount,
    question: questionQuery.data ?? null,
    current,
    answeredCount,
    correctCount,
    startedAt,
    errorMessage,
    submit,
    next,
  };
}

export function pollIntervalForStatus(
  status: SessionQuestionResponse["status"] | undefined
): number | false {
  return status === "pending" ? 1500 : false;
}
