/**
 * Quizlet paste parser tests (P2 phase 4).
 *
 * Uses the node built-in `node:test` runner so we don't need to drag in a
 * full vitest/jest setup just for one pure module. Run with:
 *   npx tsx --test apps/web/src/lib/quizlet-parser.test.ts
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { parseQuizlet } from "./quizlet-parser";

describe("parseQuizlet", () => {
  it("default (tab + newline) splits Quizlet's standard export", () => {
    const text =
      "resilience\tability to bounce back\n" +
      "perseverance\tcontinued effort despite difficulty\n";
    const r = parseQuizlet(text);
    assert.equal(r.cards.length, 2);
    assert.equal(r.malformedRowCount, 0);
    assert.deepEqual(r.cards[0], {
      term: "resilience",
      definition: "ability to bounce back",
    });
  });

  it("comma + newline splits CSV-style", () => {
    const text = "alpha,first\nbeta,second\n";
    const r = parseQuizlet(text, "\n", ",");
    assert.deepEqual(r.cards.map((c) => c.term), ["alpha", "beta"]);
  });

  it("dash + newline splits hyphen-style", () => {
    const text = "alpha-first letter\nbeta-second letter\n";
    const r = parseQuizlet(text, "\n", "-");
    assert.equal(r.cards.length, 2);
    assert.equal(r.cards[0].definition, "first letter");
  });

  it("tab + blank-line for paragraph-style cards", () => {
    const text = "alpha\tfirst\n\nbeta\tsecond\n\ngamma\tthird";
    const r = parseQuizlet(text, "\n\n", "\t");
    assert.equal(r.cards.length, 3);
    assert.equal(r.cards[2].term, "gamma");
  });

  it("mismatched delimiter surfaces malformed count", () => {
    // Tab is selected but text uses commas → every row is malformed.
    const text = "alpha,first\nbeta,second\n";
    const r = parseQuizlet(text, "\n", "\t");
    assert.equal(r.cards.length, 0);
    assert.equal(r.malformedRowCount, 2);
  });

  it("empty rows skipped", () => {
    const text = "alpha\tfirst\n\n\nbeta\tsecond\n\n";
    const r = parseQuizlet(text, "\n", "\t");
    assert.equal(r.cards.length, 2);
  });

  it("definition can be empty if delimiter is the last char", () => {
    const text = "alpha\t\n";
    const r = parseQuizlet(text, "\n", "\t");
    assert.equal(r.cards.length, 1);
    assert.equal(r.cards[0].term, "alpha");
    assert.equal(r.cards[0].definition, "");
  });

  it("preserves smart quotes and em-dashes verbatim", () => {
    const text = "résilience\tla capacité à « rebondir » — un trait clé\n";
    const r = parseQuizlet(text, "\n", "\t");
    assert.equal(r.cards[0].term, "résilience");
    assert.match(r.cards[0].definition, /« rebondir »/);
    assert.match(r.cards[0].definition, /— un trait/);
  });

  it("caps at MAX_CARDS (1000)", () => {
    const rows = Array.from(
      { length: 1500 },
      (_, i) => `term${i}\tdef${i}`,
    ).join("\n");
    const r = parseQuizlet(rows, "\n", "\t");
    assert.equal(r.cards.length, 1000);
  });
});
