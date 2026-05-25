"use client";

/**
 * MultipleChoiceCard.
 *
 * Owns its own answer state. Calls `/questions/{id}/check` server action via
 * the parent's onSubmit prop, then locks selection and shows feedback. Result
 * (correct boolean) bubbles up via `onResult` so the parent can advance the
 * round, update ELO, etc.
 */
import { useState } from "react";

import type { MCQData, QuestionCheckResponse } from "@/lib/types";

interface MultipleChoiceCardProps {
  questionId: number;
  data: MCQData;
  onCheck: (questionId: number, selectedIndex: number) => Promise<QuestionCheckResponse>;
  onResult?: (correct: boolean) => void;
}

export function MultipleChoiceCard({
  questionId,
  data,
  onCheck,
  onResult,
}: MultipleChoiceCardProps) {
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<QuestionCheckResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    if (selected === null || submitting) return;
    setSubmitting(true);
    try {
      const r = await onCheck(questionId, selected);
      setResult(r);
      onResult?.(r.correct);
    } finally {
      setSubmitting(false);
    }
  }

  const locked = result !== null;

  return (
    <div className="rounded border border-gray-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-base font-medium">{data.stem}</h3>

      <div className="space-y-2">
        {data.options.map((opt, i) => {
          const isPicked = selected === i;
          const isCorrect = locked && i === result.correct_index;
          const isWrong = locked && isPicked && i !== result.correct_index;
          const base =
            "flex w-full items-start gap-2 rounded border px-3 py-2 text-left text-sm";
          const cls = isCorrect
            ? "border-green-500 bg-green-50"
            : isWrong
              ? "border-red-500 bg-red-50"
              : isPicked
                ? "border-black bg-gray-50"
                : "border-gray-300 hover:border-gray-400";
          return (
            <button
              key={i}
              type="button"
              disabled={locked}
              onClick={() => setSelected(i)}
              className={`${base} ${cls}`}
            >
              <span className="font-mono text-xs text-gray-500">
                {String.fromCharCode(65 + i)}.
              </span>
              <span>{opt}</span>
            </button>
          );
        })}
      </div>

      {!locked ? (
        <button
          type="button"
          disabled={selected === null || submitting}
          onClick={submit}
          className="mt-4 rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:bg-gray-300"
        >
          {submitting ? "Checking…" : "Submit"}
        </button>
      ) : (
        <div
          className={`mt-4 rounded p-3 text-sm ${
            result.correct
              ? "bg-green-50 text-green-900"
              : "bg-red-50 text-red-900"
          }`}
        >
          <p className="font-medium">
            {result.correct ? "Correct" : "Incorrect"}
          </p>
          {result.explanation && (
            <p className="mt-1 text-sm">{result.explanation}</p>
          )}
        </div>
      )}
    </div>
  );
}
