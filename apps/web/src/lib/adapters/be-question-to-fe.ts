import type { MCQDataPublic, SessionQuestionPayload, SubmitAnswerResponse } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";

export function beQuestionToFe(payload: SessionQuestionPayload): FeQuestion {
  const data = payload.data as MCQDataPublic;
  return {
    id: payload.id,
    senseId: payload.definition_id,
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
  correct: boolean,
  result?: SubmitAnswerResponse
): FeQuestion {
  const base = beQuestionToFe(payload);
  const correctAnswer = base.options?.[correctIndex] ?? "";
  const reveal = (result?.reveal ?? {}) as {
    distractor_rationale?: string[];
    explanation?: string;
  };
  return {
    ...base,
    definition: correctAnswer,
    correctAnswer,
    userAnswer: base.options?.[selectedIndex],
    isCorrect: correct,
    distractorRationale: Array.isArray(reveal.distractor_rationale)
      ? reveal.distractor_rationale
      : undefined,
    feedback: result?.feedback ?? reveal.explanation ?? result?.explanation ?? undefined,
    score: result?.score,
  };
}
