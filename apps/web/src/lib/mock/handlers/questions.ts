// Mock handlers for questions — mirrors routes/questions.py.
// GET /definitions/:id/question  → fetch-or-ready (always ready in mock)
// POST /questions/:id/check      → reveal correctness

import { getState } from "../store";
import type { StoreQuestion } from "../types";
import type {
  QuestionCheckResponse,
  QuestionFetchResponse,
  QuestionRead,
} from "@/types/domain";

function toQuestionRead(q: StoreQuestion): QuestionRead {
  return {
    id: q.id,
    definition_id: q.definition_id,
    type: q.type,
    // pre-submit projection: stem + options only (no answer fields)
    data: { stem: q.stem, options: q.options },
    created_at: q.created_at,
  };
}

export function fetchOrEnqueueQuestion(
  definitionId: number,
): QuestionFetchResponse {
  const { questions, questionByDefinition } = getState();
  const qId = questionByDefinition[definitionId];
  const q = qId ? questions[qId] : undefined;
  if (!q) {
    // mirror the BE "generating" contract; in practice the seed always has one
    return { question: null, status: "pending" };
  }
  return { question: toQuestionRead(q), status: "ready" };
}

export function checkAnswer(
  questionId: string,
  selectedIndex: number,
): QuestionCheckResponse {
  const { questions } = getState();
  const q = questions[questionId];
  if (!q) throw Object.assign(new Error("question_not_found"), { __status: 404 });
  return {
    correct: selectedIndex === q.correct_index,
    explanation: q.explanation,
    correct_index: q.correct_index,
  };
}
