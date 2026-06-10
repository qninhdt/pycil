/**
 * Mock router + store integration tests.
 *
 * Uses the node built-in `node:test` runner (matches quizlet-parser.test.ts).
 * The store falls back to in-memory state under Node (no localStorage), so the
 * handlers run end-to-end without a DOM. Run with:
 *   npx tsx --test apps/web/src/lib/mock/router.test.ts
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

function firstDeck(): NodeRead {
  const roots = handle("GET", "/nodes/root") as NodeRead[];
  const folder = roots.find((n) => n.type === "FOLDER");
  assert.ok(folder, "seed has at least one folder");
  const kids = handle("GET", `/nodes/${folder.id}/children`) as NodeRead[];
  const deck = kids.find((n) => n.type === "DECK");
  assert.ok(deck, "folder has at least one deck");
  return deck;
}

describe("mock router — nodes", () => {
  it("seeds root folders + decks", () => {
    resetStore();
    const roots = handle("GET", "/nodes/root") as NodeRead[];
    assert.ok(roots.length > 0, "root nodes seeded");
    assert.ok(roots.some((n) => n.type === "FOLDER"), "has a folder");
  });

  it("builds a breadcrumb for a nested deck", () => {
    resetStore();
    const deck = firstDeck();
    assert.ok(deck.breadcrumb.length >= 2, "deck breadcrumb has folder + deck");
    assert.equal(deck.breadcrumb.at(-1)?.id, deck.id, "last crumb is the deck");
  });

  it("CRUD round-trips: create → rename → star → pin → delete", () => {
    resetStore();
    const before = (handle("GET", "/nodes/root") as NodeRead[]).length;

    const created = handle("POST", "/nodes", {
      type: "DECK",
      name: "Test Deck",
    }) as NodeRead;
    assert.equal(created.name, "Test Deck");
    assert.equal(created.is_starred, false);
    assert.equal(
      (handle("GET", "/nodes/root") as NodeRead[]).length,
      before + 1,
      "create adds a root node",
    );

    const renamed = handle("PATCH", `/nodes/${created.id}`, {
      name: "Renamed",
    }) as NodeRead;
    assert.equal(renamed.name, "Renamed");

    const starred = handle("POST", `/nodes/${created.id}/star`) as NodeRead;
    assert.equal(starred.is_starred, true);
    const pinned = handle("POST", `/nodes/${created.id}/pin`) as NodeRead;
    assert.equal(pinned.is_pinned, true);

    handle("DELETE", `/nodes/${created.id}`);
    assert.equal(
      (handle("GET", "/nodes/root") as NodeRead[]).length,
      before,
      "delete removes the node",
    );
  });

  it("404s on unknown node and unknown route", () => {
    resetStore();
    assert.throws(() => handle("GET", "/nodes/does-not-exist"), /not_found/);
    assert.throws(() => handle("GET", "/totally/unknown"), /not_found/);
  });
});

describe("mock router — terms (synchronous enrichment)", () => {
  it("lists deck terms already enriched (no pending job)", () => {
    resetStore();
    const deck = firstDeck();
    const rows = handle("GET", `/decks/${deck.id}/terms`) as DeckTermRead[];
    assert.ok(rows.length > 0, "deck has terms");
    assert.ok(rows[0].definition, "term has a definition");
    assert.equal(rows[0].job_status, "completed");
    assert.equal(rows[0].job_id, null);
  });

  it("addTerm completes enrichment synchronously", () => {
    resetStore();
    const deck = firstDeck();
    const res = handle("POST", `/decks/${deck.id}/terms`, {
      value: "serene",
    }) as { term: { value: string }; job_id: string | null };
    assert.equal(res.term.value, "serene");
    assert.equal(res.job_id, null, "no enrichment job in mock mode");

    const rows = handle("GET", `/decks/${deck.id}/terms`) as DeckTermRead[];
    const added = rows.find((r) => r.term.value === "serene");
    assert.ok(added?.definition, "new term immediately has a definition");
  });
});

describe("mock router — questions", () => {
  it("fetches a ready question and checks an answer", () => {
    resetStore();
    const deck = firstDeck();
    const rows = handle("GET", `/decks/${deck.id}/terms`) as DeckTermRead[];
    const defId = (rows[0].definition as { id: number }).id;

    const q = handle(
      "GET",
      `/definitions/${defId}/question`,
    ) as QuestionFetchResponse;
    assert.equal(q.status, "ready");
    assert.ok(q.question, "question present");
    const data = q.question!.data as { options: string[] };
    assert.equal(data.options.length, 4);

    const check = handle("POST", `/questions/${q.question!.id}/check`, {
      selected_index: 0,
    }) as { correct: boolean; correct_index: number };
    assert.equal(typeof check.correct, "boolean");
    assert.ok(check.correct_index >= 0 && check.correct_index <= 3);
  });
});

describe("mock router — learning session (round math matches backend)", () => {
  it("starts, paginates rounds, and completes", () => {
    resetStore();
    const deck = firstDeck();
    const start = handle("POST", `/decks/${deck.id}/sessions`, {
      session_size: 8,
    }) as StartSessionResponse;
    assert.equal(start.selected_count, 8);

    // First question: round 0, position 0, size = min(5, 8) = 5 remaining.
    const q1 = handle(
      "GET",
      `/sessions/${start.session_id}/question`,
    ) as SessionQuestionResponse;
    assert.equal(q1.status, "ready");
    assert.equal(q1.round_index, 0);
    assert.equal(q1.round_position, 0, "backend always returns position 0");
    assert.equal(q1.round_size, 5, "round_size = remaining in round");
    assert.ok(
      (q1.question as { definition_id?: number }).definition_id !== undefined,
      "question carries definition_id",
    );

    // Answer 4 → still round 0, remaining shrinks 5 → 1.
    for (let i = 0; i < 4; i++) {
      const sq = handle(
        "GET",
        `/sessions/${start.session_id}/question`,
      ) as SessionQuestionResponse;
      handle("POST", `/sessions/${start.session_id}/answer`, {
        question_id: (sq.question as { id: string }).id,
        selected_index: 0,
      });
    }
    const q6 = handle(
      "GET",
      `/sessions/${start.session_id}/question`,
    ) as SessionQuestionResponse;
    assert.equal(q6.round_size, 1, "round_size shrinks to 1");

    // 5th answer closes round 0.
    const a5 = handle("POST", `/sessions/${start.session_id}/answer`, {
      question_id: (q6.question as { id: string }).id,
      selected_index: 0,
    }) as SubmitAnswerResponse;
    assert.equal(a5.round_complete, true, "round 0 completes at the boundary");
    assert.ok(a5.term_reviewed, "answer carries term_reviewed");
    assert.equal(typeof a5.term_reviewed!.elo_new, "number");

    const q7 = handle(
      "GET",
      `/sessions/${start.session_id}/question`,
    ) as SessionQuestionResponse;
    assert.equal(q7.round_index, 1, "advanced to round 1");
    assert.equal(q7.round_size, 3, "round 1 has 8 - 5 = 3 remaining");

    // Drain to completion.
    let safety = 0;
    let completed = false;
    while (safety++ < 20) {
      const sq = handle(
        "GET",
        `/sessions/${start.session_id}/question`,
      ) as SessionQuestionResponse;
      if (sq.status === "session_complete") {
        completed = true;
        break;
      }
      const ans = handle("POST", `/sessions/${start.session_id}/answer`, {
        question_id: (sq.question as { id: string }).id,
        selected_index: 0,
      }) as SubmitAnswerResponse;
      if (ans.session_complete) {
        completed = true;
        break;
      }
    }
    assert.ok(completed, "session runs to completion");
  });
});

describe("mock router — me", () => {
  it("returns the demo user and applies patches", () => {
    resetStore();
    const me = handle("GET", "/me") as { email: string; name: string | null };
    assert.equal(me.email, "demo@pycil.app");
    const upd = handle("PATCH", "/me", { name: "New Name" }) as {
      name: string | null;
    };
    assert.equal(upd.name, "New Name");
  });
});
