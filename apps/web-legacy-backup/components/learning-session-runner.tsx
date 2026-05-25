"use client";

/**
 * Learning session orchestrator.
 *
 * Holds the loop: fetch next question → render MCQ → submit → show feedback
 * → fetch next. Polls if backend reports `pending` (LLM still generating).
 * Round + session summaries surface ELO deltas + mastery jumps.
 */
import { useEffect, useRef, useState } from "react";

import { MultipleChoiceCard } from "@/components/multiple-choice-card";
import {
  nextQuestionAction,
  submitAnswerAction,
} from "@/lib/learning-actions";
import type {
  SessionQuestionResponse,
  SubmitAnswerResponse,
  TermReviewedResult,
} from "@/lib/types";

type Phase =
  | { kind: "loading" }
  | { kind: "pending" }
  | { kind: "question"; payload: SessionQuestionResponse }
  | { kind: "feedback"; result: SubmitAnswerResponse }
  | { kind: "round_summary"; reviewed: TermReviewedResult[] }
  | { kind: "session_complete"; reviewed: TermReviewedResult[] }
  | { kind: "error"; message: string };

const POLL_DELAY_MS = 1500;

export function LearningSessionRunner({ sessionId }: { sessionId: string }) {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [reviewedAcc, setReviewedAcc] = useState<TermReviewedResult[]>([]);
  const [roundReviewed, setRoundReviewed] = useState<TermReviewedResult[]>([]);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function fetchNext() {
    setPhase({ kind: "loading" });
    try {
      const r = await nextQuestionAction(sessionId);
      if (r.status === "session_complete") {
        setPhase({ kind: "session_complete", reviewed: reviewedAcc });
        return;
      }
      if (r.status === "pending" || r.question === null) {
        setPhase({ kind: "pending" });
        pollTimerRef.current = setTimeout(() => {
          pollTimerRef.current = null;
          void fetchNext();
        }, POLL_DELAY_MS);
        return;
      }
      setPhase({ kind: "question", payload: r });
    } catch (e) {
      setPhase({ kind: "error", message: String(e) });
    }
  }

  useEffect(() => {
    void fetchNext();
    return () => {
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function onCheck(_questionId: string, selected: number) {
    if (phase.kind !== "question" || !phase.payload.question) {
      throw new Error("no_active_question");
    }
    const result = await submitAnswerAction(
      sessionId,
      phase.payload.question.id,
      selected
    );
    if (result.term_reviewed) {
      setReviewedAcc((prev) => [...prev, result.term_reviewed!]);
      setRoundReviewed((prev) => [...prev, result.term_reviewed!]);
    }
    setPhase({ kind: "feedback", result });
    return {
      correct: result.correct,
      explanation: result.explanation,
      correct_index: result.correct_index,
    };
  }

  function continueAfterFeedback() {
    if (phase.kind !== "feedback") return;
    if (phase.result.session_complete) {
      setPhase({ kind: "session_complete", reviewed: reviewedAcc });
      return;
    }
    if (phase.result.round_complete) {
      setPhase({ kind: "round_summary", reviewed: roundReviewed });
      return;
    }
    void fetchNext();
  }

  if (phase.kind === "loading") {
    return <p className="text-sm text-gray-500">Loading next question…</p>;
  }
  if (phase.kind === "pending") {
    return (
      <p className="text-sm text-gray-500">
        Generating question for the next term…
      </p>
    );
  }
  if (phase.kind === "error") {
    return <p className="text-sm text-red-600">Error: {phase.message}</p>;
  }
  if (phase.kind === "session_complete") {
    return <SessionSummary reviewed={phase.reviewed} />;
  }
  if (phase.kind === "round_summary") {
    return (
      <RoundSummary
        reviewed={phase.reviewed}
        onContinue={() => {
          setRoundReviewed([]);
          void fetchNext();
        }}
      />
    );
  }
  if (phase.kind === "feedback") {
    return (
      <FeedbackView result={phase.result} onContinue={continueAfterFeedback} />
    );
  }

  // phase.kind === "question"
  const q = phase.payload.question!;
  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-500">
        Round {phase.payload.round_index} ·{" "}
        {phase.payload.round_size} term(s) remaining
      </div>
      <MultipleChoiceCard
        questionId={q.id}
        data={q.data}
        onCheck={async (qid, sel) => onCheck(qid as string, sel)}
      />
    </div>
  );
}


function FeedbackView({
  result,
  onContinue,
}: {
  result: SubmitAnswerResponse;
  onContinue: () => void;
}) {
  return (
    <div className="space-y-4">
      <div
        className={`rounded p-4 ${
          result.correct
            ? "bg-green-50 text-green-900"
            : "bg-red-50 text-red-900"
        }`}
      >
        <p className="font-medium">
          {result.correct ? "Correct" : "Not quite"}
        </p>
        {result.explanation && (
          <p className="mt-1 text-sm">{result.explanation}</p>
        )}
      </div>
      {result.term_reviewed && (
        <div className="rounded border border-gray-200 bg-white p-4 text-sm">
          <p className="font-medium">Term reviewed</p>
          <p className="text-gray-600">
            ELO {result.term_reviewed.elo_old} → {result.term_reviewed.elo_new}{" "}
            (Δ {result.term_reviewed.elo_delta}) · level{" "}
            {result.term_reviewed.mastery_level}
          </p>
        </div>
      )}
      <button
        type="button"
        onClick={onContinue}
        className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
      >
        Continue
      </button>
    </div>
  );
}


function RoundSummary({
  reviewed,
  onContinue,
}: {
  reviewed: TermReviewedResult[];
  onContinue: () => void;
}) {
  return (
    <div className="space-y-4 rounded border border-gray-200 bg-white p-6">
      <h2 className="text-lg font-medium">Round complete</h2>
      <p className="text-sm text-gray-600">
        {reviewed.length} term(s) reached mastery this round.
      </p>
      <button
        type="button"
        onClick={onContinue}
        className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
      >
        Next round
      </button>
    </div>
  );
}


function SessionSummary({ reviewed }: { reviewed: TermReviewedResult[] }) {
  const avgDelta =
    reviewed.length === 0
      ? 0
      : Math.round(
          reviewed.reduce((s, r) => s + r.elo_delta, 0) / reviewed.length
        );
  return (
    <div className="space-y-4 rounded border border-gray-200 bg-white p-6">
      <h2 className="text-lg font-medium">Session complete</h2>
      <p className="text-sm text-gray-600">
        Reviewed {reviewed.length} term(s). Avg ELO Δ: {avgDelta}.
      </p>
      <a
        href="/dashboard"
        className="inline-block rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
      >
        Back to dashboard
      </a>
    </div>
  );
}
