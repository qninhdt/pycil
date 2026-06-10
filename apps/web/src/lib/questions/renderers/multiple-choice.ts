import { MultipleChoiceQuestion } from "@/components/study/learn/multiple-choice-question";
import type { MCQDataPublic, SessionQuestionPayload } from "@/types/domain";
import type { Question as FeQuestion } from "@/types/learning";
import { register, type QuestionRenderer } from "../registry";

const mcqRenderer: QuestionRenderer = {
  type: "MULTIPLE_CHOICE",
  Component: MultipleChoiceQuestion,
  gradingMode: "sync",
  toFe(payload: SessionQuestionPayload): FeQuestion {
    const data = payload.data as MCQDataPublic;
    return {
      id: payload.id,
      type: "MULTIPLE_CHOICE",
      term: data.stem,
      definition: "",
      options: [...data.options],
      correctAnswer: "",
    };
  },
  encodeAnswer(answer: string, question: FeQuestion) {
    const idx = question.options?.indexOf(answer) ?? -1;
    return { selected_index: idx };
  },
};

register(mcqRenderer);

export default mcqRenderer;
