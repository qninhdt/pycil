import type { MCQData, SessionQuestionPayload } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";

export function beQuestionToFe(payload: SessionQuestionPayload): FeQuestion {
  const data = payload.data as MCQData;
  return {
    id: payload.id,
    type: "multiple-choice",
    term: data.stem,
    definition: data.options[data.correct_index] ?? "",
    options: [...data.options],
    correctAnswer: data.options[data.correct_index] ?? "",
  };
}

export function beQuestionWithResultToFe(
  payload: SessionQuestionPayload,
  selectedIndex: number,
  correctIndex: number,
  correct: boolean
): FeQuestion {
  const base = beQuestionToFe(payload);
  return {
    ...base,
    correctAnswer: base.options?.[correctIndex] ?? base.correctAnswer,
    userAnswer: base.options?.[selectedIndex],
    isCorrect: correct,
  };
}
