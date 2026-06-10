import { MultipleChoiceQuestion } from "@/components/study/learn/multiple-choice-question";
import type { SessionQuestionPayload } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";
import { register, type QuestionRenderer } from "../registry";

type FillDataPublic = { prompt: string };

// Rule-based (sync) single-word recall. Reuses the MCQ shell as a placeholder
// Component; the cloze input UI lives in fill-in-blank-question.tsx.
const fillRenderer: QuestionRenderer = {
  type: "FILL_IN_BLANK",
  Component: MultipleChoiceQuestion,
  gradingMode: "sync",
  toFe(payload: SessionQuestionPayload): FeQuestion {
    const data = payload.data as FillDataPublic;
    return {
      id: payload.id,
      type: "FILL_IN_BLANK",
      term: data.prompt ?? "",
      definition: "",
      correctAnswer: "",
    };
  },
  encodeAnswer(answer: string) {
    return { user_answer: answer };
  },
};

register(fillRenderer);

export default fillRenderer;
