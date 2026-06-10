/**
 * Question renderer registry. Importing this module self-registers all builtin
 * question-type renderers. Resolve a renderer with ``get(type)``.
 */
import "./renderers/multiple-choice";
import "./renderers/write";
import "./renderers/fill-in-blank";

export { get, register, allTypes } from "./registry";
export type {
  QuestionRenderer,
  QuestionComponentProps,
  AnswerPayload,
} from "./registry";
