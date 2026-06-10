/**
 * Schema-parity guard: asserts every mock read payload contains the required
 * field set of its FE domain type. The FE domain types (`@/types/domain/*`) are
 * the build-time mirror of the backend Pydantic schemas, so if the mock drops a
 * field the backend returns, this fails loudly — protecting the "flip one env
 * var to switch to the real backend" guarantee.
 *
 * Uses `node:test`. Run with:
 *   npx tsx --test apps/web/src/lib/mock/schema-parity.test.ts
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { handle } from "./router";
import { resetStore } from "./store";
import type {
  DeckTermRead,
  NodeRead,
  QuestionFetchResponse,
  SessionQuestionResponse,
  StartSessionResponse,
  SubmitAnswerResponse,
} from "@/types/domain";

/** Assert `obj` has every key in `required` (superset check, not exact). */
function assertHasKeys(
  obj: Record<string, unknown>,
  required: string[],
  label: string,
): void {
  for (const key of required) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(obj, key),
      `${label}: missing required field "${key}"`,
    );
  }
}

// Required field sets mirror apps/pycil-core/pycil_core/schemas/*.py and the FE
// types/domain/* read models. Keep in sync with the backend Read schemas.
const NODE_READ_KEYS = [
  "id",
  "type",
  "name",
  "description",
  "parent_node_id",
  "visibility",
  "definition_count",
  "is_starred",
  "is_pinned",
  "created_at",
  "updated_at",
  "breadcrumb",
];

const DECK_TERM_READ_KEYS = ["term", "position", "definition", "job_id", "job_status"];
const TERM_READ_KEYS = ["id", "value", "type", "created_at", "updated_at"];

const QUESTION_READ_KEYS = ["id", "definition_id", "type", "data", "created_at"];

const START_SESSION_KEYS = ["session_id", "deck_id", "selected_count"];
const SESSION_QUESTION_KEYS = [
  "question",
  "status",
  "round_index",
  "round_position",
  "round_size",
];
const SUBMIT_ANSWER_KEYS = [
  "correct",
  "explanation",
  "correct_index",
  "round_complete",
  "session_complete",
  "term_reviewed",
];
const TERM_REVIEWED_KEYS = [
  "definition_id",
  "elo_old",
  "elo_new",
  "elo_delta",
  "next_review_date",
  "interval_seconds",
  "mastery_level",
];
const CURRENT_USER_KEYS = ["id", "email", "name", "image"];

function firstDeck(): NodeRead {
  const roots = handle("GET", "/nodes/root") as NodeRead[];
  const folder = roots.find((n) => n.type === "FOLDER")!;
  const kids = handle("GET", `/nodes/${folder.id}/children`) as NodeRead[];
  return kids.find((n) => n.type === "DECK")!;
}

describe("schema parity — nodes", () => {
  it("NodeRead has all required fields", () => {
    resetStore();
    const roots = handle("GET", "/nodes/root") as NodeRead[];
    for (const node of roots) {
      assertHasKeys(node as unknown as Record<string, unknown>, NODE_READ_KEYS, "NodeRead");
      assert.ok(Array.isArray(node.breadcrumb), "breadcrumb is an array");
    }
  });
});

describe("schema parity — terms", () => {
  it("DeckTermRead + nested TermRead have all required fields", () => {
    resetStore();
    const deck = firstDeck();
    const rows = handle("GET", `/decks/${deck.id}/terms`) as DeckTermRead[];
    assert.ok(rows.length > 0);
    for (const row of rows) {
      assertHasKeys(row as unknown as Record<string, unknown>, DECK_TERM_READ_KEYS, "DeckTermRead");
      assertHasKeys(row.term as unknown as Record<string, unknown>, TERM_READ_KEYS, "TermRead");
    }
  });

  it("TermAddResponse has term + job_id", () => {
    resetStore();
    const deck = firstDeck();
    const res = handle("POST", `/decks/${deck.id}/terms`, { value: "lucid" }) as Record<string, unknown>;
    assertHasKeys(res, ["term", "job_id"], "TermAddResponse");
    assertHasKeys(res.term as Record<string, unknown>, TERM_READ_KEYS, "TermAddResponse.term");
  });
});

describe("schema parity — questions", () => {
  it("QuestionFetchResponse + QuestionRead have all required fields", () => {
    resetStore();
    const deck = firstDeck();
    const rows = handle("GET", `/decks/${deck.id}/terms`) as DeckTermRead[];
    const defId = (rows[0].definition as { id: number }).id;
    const q = handle("GET", `/definitions/${defId}/question`) as QuestionFetchResponse;
    assertHasKeys(q as unknown as Record<string, unknown>, ["question", "status"], "QuestionFetchResponse");
    assert.ok(q.question, "question present");
    assertHasKeys(q.question as unknown as Record<string, unknown>, QUESTION_READ_KEYS, "QuestionRead");

    const check = handle("POST", `/questions/${q.question!.id}/check`, { selected_index: 0 }) as Record<string, unknown>;
    assertHasKeys(check, ["correct", "explanation", "correct_index"], "QuestionCheckResponse");
  });
});

describe("schema parity — learning", () => {
  it("StartSessionResponse has all required fields", () => {
    resetStore();
    const deck = firstDeck();
    const start = handle("POST", `/decks/${deck.id}/sessions`, { session_size: 5 }) as StartSessionResponse;
    assertHasKeys(start as unknown as Record<string, unknown>, START_SESSION_KEYS, "StartSessionResponse");
  });

  it("SessionQuestionResponse + SubmitAnswerResponse + TermReviewedResult parity", () => {
    resetStore();
    const deck = firstDeck();
    const start = handle("POST", `/decks/${deck.id}/sessions`, { session_size: 5 }) as StartSessionResponse;
    const sq = handle("GET", `/sessions/${start.session_id}/question`) as SessionQuestionResponse;
    assertHasKeys(sq as unknown as Record<string, unknown>, SESSION_QUESTION_KEYS, "SessionQuestionResponse");

    const ans = handle("POST", `/sessions/${start.session_id}/answer`, {
      question_id: (sq.question as { id: string }).id,
      selected_index: 0,
    }) as SubmitAnswerResponse;
    assertHasKeys(ans as unknown as Record<string, unknown>, SUBMIT_ANSWER_KEYS, "SubmitAnswerResponse");
    assert.ok(ans.term_reviewed, "term_reviewed present");
    assertHasKeys(ans.term_reviewed as unknown as Record<string, unknown>, TERM_REVIEWED_KEYS, "TermReviewedResult");
  });
});

describe("schema parity — me", () => {
  it("CurrentUser has all required fields", () => {
    resetStore();
    const me = handle("GET", "/me") as Record<string, unknown>;
    assertHasKeys(me, CURRENT_USER_KEYS, "CurrentUser");
  });
});
