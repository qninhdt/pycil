import type { ComponentType } from "react";
import type { Question as FeQuestion } from "@/types/learning";
import type { SessionQuestionPayload } from "@/types/domain";

/** Props every question-type renderer component receives. */
export interface QuestionComponentProps {
  question: FeQuestion;
  onAnswer: (answer: string) => void;
  showResult?: boolean;
  className?: string;
}

/** The answer payload sent to the backend submit endpoint. */
export type AnswerPayload =
  | { selected_index: number }
  | { user_answer: string };

/**
 * A question-type renderer. Adding a new question type = add a renderer module
 * and register() it — no edits to the learning session component.
 */
export interface QuestionRenderer {
  /** Matches the backend ``type_id`` (e.g. "MULTIPLE_CHOICE"). */
  type: string;
  /** Renders the prompt + collects the answer. */
  Component: ComponentType<QuestionComponentProps>;
  /** Adapt a backend question payload into the FE question shape. */
  toFe: (payload: SessionQuestionPayload) => FeQuestion;
  /** Encode the UI answer into the backend submit payload. */
  encodeAnswer: (answer: string, question: FeQuestion) => AnswerPayload;
  /** sync = inline verdict; async = server-graded (SSE-streamed). */
  gradingMode: "sync" | "async";
}

const _REGISTRY = new Map<string, QuestionRenderer>();

export function register(renderer: QuestionRenderer): void {
  _REGISTRY.set(renderer.type, renderer);
}

export function get(type: string): QuestionRenderer | undefined {
  return _REGISTRY.get(type);
}

export function allTypes(): string[] {
  return [..._REGISTRY.keys()].sort();
}
