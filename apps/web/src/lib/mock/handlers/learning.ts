// Mock handlers for learning sessions — mirrors routes/learning.py.
// POST /decks/:id/sessions        → start
// GET  /sessions/:id/question     → next MCQ or session_complete
// POST /sessions/:id/answer       → grade + advance + term_reviewed

import { getState, commit } from "../store";
import { newUuid } from "../id";
import type { StoreSession } from "../types";
import type {
  StartSessionResponse,
  SessionQuestionResponse,
  SubmitAnswerResponse,
  TermReviewedResult,
} from "@/types/domain";

const DEFAULT_ROUND_SIZE = 5;

function notFound(msg: string): Error {
  return Object.assign(new Error(msg), { __status: 404 });
}

export function startSession(
  deckId: string,
  sessionSize = 20,
): StartSessionResponse {
  const state = getState();
  const defIds = Object.values(state.terms)
    .filter((t) => t.deck_id === deckId && t.definition_id !== null)
    .sort((a, b) => a.position - b.position)
    .map((t) => t.definition_id as number)
    .slice(0, sessionSize);

  const id = newUuid();
  const session: StoreSession = {
    id,
    deck_id: deckId,
    definition_ids: defIds,
    cursor: 0,
    round_index: 0,
    round_start: 0,
    answered: 0,
    correct: 0,
  };
  state.sessions[id] = session;
  commit();
  return { session_id: id, deck_id: deckId, selected_count: defIds.length };
}

export function getSessionQuestion(
  sessionId: string,
): SessionQuestionResponse {
  const { sessions, questionByDefinition, questions } = getState();
  const session = sessions[sessionId];
  if (!session) throw notFound("session_not_found");

  // Backend contract: round_position is always 0 and round_size is the count
  // of items REMAINING in the current round (shrinks as the round is consumed).
  const roundEnd = Math.min(
    session.round_start + DEFAULT_ROUND_SIZE,
    session.definition_ids.length,
  );
  const remainingInRound = Math.max(0, roundEnd - session.cursor);

  if (session.cursor >= session.definition_ids.length) {
    return {
      question: null,
      status: "session_complete",
      round_index: session.round_index,
      round_position: 0,
      round_size: 0,
    };
  }

  const defId = session.definition_ids[session.cursor];
  const qId = questionByDefinition[defId];
  const q = qId ? questions[qId] : undefined;
  if (!q) {
    return {
      question: null,
      status: "pending",
      round_index: session.round_index,
      round_position: 0,
      round_size: remainingInRound,
    };
  }

  return {
    question: {
      id: q.id,
      definition_id: q.definition_id,
      type: q.type,
      data: { stem: q.stem, options: q.options },
    },
    status: "ready",
    round_index: session.round_index,
    round_position: 0,
    round_size: remainingInRound,
  };
}

function buildTermReviewed(
  definitionId: number,
  correct: boolean,
): TermReviewedResult {
  const eloOld = 1200;
  const eloDelta = correct ? 18 : -12;
  const intervalSeconds = correct ? 86_400 * 3 : 86_400;
  return {
    definition_id: definitionId,
    elo_old: eloOld,
    elo_new: eloOld + eloDelta,
    elo_delta: eloDelta,
    next_review_date: new Date(Date.now() + intervalSeconds * 1000).toISOString(),
    interval_seconds: intervalSeconds,
    mastery_level: correct ? 4 : 2,
  };
}

export function submitAnswer(
  sessionId: string,
  questionId: string,
  selectedIndex: number,
): SubmitAnswerResponse {
  const state = getState();
  const session = state.sessions[sessionId];
  if (!session) throw notFound("session_not_found");
  const q = state.questions[questionId];
  if (!q) throw notFound("question_not_found");

  const correct = selectedIndex === q.correct_index;
  session.answered += 1;
  if (correct) session.correct += 1;
  session.cursor += 1;

  const sessionComplete = session.cursor >= session.definition_ids.length;
  // A round is DEFAULT_ROUND_SIZE items; it completes when the cursor reaches
  // the next round boundary (and the session isn't over).
  const roundComplete =
    !sessionComplete &&
    session.cursor >= session.round_start + DEFAULT_ROUND_SIZE;
  if (roundComplete) {
    session.round_index += 1;
    session.round_start = session.cursor;
  }

  commit();

  return {
    correct,
    explanation: q.explanation,
    correct_index: q.correct_index,
    round_complete: roundComplete,
    session_complete: sessionComplete,
    term_reviewed: buildTermReviewed(q.definition_id, correct),
  };
}
