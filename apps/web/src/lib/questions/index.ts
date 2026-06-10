/**
 * Question renderer registry. Importing this module self-registers all builtin
 * question-type renderers. Resolve a renderer with ``get(type)``.
 */
import "./renderers/multiple-choice";

export { get, register, allTypes } from "./registry";
export type {
  QuestionRenderer,
  QuestionComponentProps,
  AnswerPayload,
} from "./registry";
