import type { MCQDataPublic, SessionQuestionPayload } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";

export function beQuestionToFe(payload: SessionQuestionPayload): FeQuestion {
  const data = payload.data as MCQDataPublic;
  return {
    id: payload.id,
    type: "multiple-choice",
    term: data.stem,
    definition: "",
    options: [...data.options],
    correctAnswer: "",
  };
}

export function beQuestionWithResultToFe(
  payload: SessionQuestionPayload,
  selectedIndex: number,
  correctIndex: number,
  correct: boolean
): FeQuestion {
  const base = beQuestionToFe(payload);
  const correctAnswer = base.options?.[correctIndex] ?? "";
  return {
    ...base,
    definition: correctAnswer,
    correctAnswer,
    userAnswer: base.options?.[selectedIndex],
    isCorrect: correct,
  };
}
