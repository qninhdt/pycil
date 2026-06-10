import { MultipleChoiceQuestion } from "@/components/study/learn/multiple-choice-question";
import type { SessionQuestionPayload } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";
import { register, type QuestionRenderer } from "../registry";

type WriteDataPublic = { prompt: string };

// Reuses the MCQ shell as a placeholder Component; the free-text input UI is
// wired in write-question.tsx and selected by the session via gradingMode.
const writeRenderer: QuestionRenderer = {
  type: "WRITE",
  Component: MultipleChoiceQuestion,
  gradingMode: "async",
  toFe(payload: SessionQuestionPayload): FeQuestion {
    const data = payload.data as WriteDataPublic;
    return {
      id: payload.id,
      type: "WRITE",
      term: data.prompt ?? "",
      definition: "",
      correctAnswer: "",
    };
  },
  encodeAnswer(answer: string) {
    return { user_answer: answer };
  },
};

register(writeRenderer);

export default writeRenderer;
