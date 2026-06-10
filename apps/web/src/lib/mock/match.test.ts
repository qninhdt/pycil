/**
 * Path matcher unit tests. The router depends on these semantics: `:param`
 * extraction, exact-segment matching, and segment-count discrimination (so
 * `/nodes/root` and `/nodes/:id` stay distinguishable by route order).
 *
 * Uses `node:test`. Run with:
 *   npx tsx --test apps/web/src/lib/mock/match.test.ts
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { matchRoute } from "./match";

describe("matchRoute", () => {
  it("matches a static path", () => {
    const m = matchRoute("/nodes/root", "/nodes/root");
    assert.ok(m);
    assert.deepEqual(m!.params, {});
  });

  it("extracts a single param", () => {
    const m = matchRoute("/nodes/:id", "/nodes/abc-123");
    assert.ok(m);
    assert.equal(m!.params.id, "abc-123");
  });

  it("extracts a param in a longer path", () => {
    const m = matchRoute("/nodes/:id/children", "/nodes/xyz/children");
    assert.ok(m);
    assert.equal(m!.params.id, "xyz");
  });

  it("rejects on segment-count mismatch", () => {
    assert.equal(matchRoute("/nodes/:id", "/nodes/a/b"), null);
    assert.equal(matchRoute("/nodes/:id/children", "/nodes/a"), null);
  });

  it("does not match a different static segment", () => {
    // /nodes/root vs /nodes/:id are both 2-segment — the matcher matches BOTH
    // a static and a param pattern, so route ORDER (root before :id) matters.
    assert.ok(matchRoute("/nodes/root", "/nodes/root"));
    assert.ok(matchRoute("/nodes/:id", "/nodes/root")); // param also matches
    assert.equal(matchRoute("/nodes/root", "/nodes/other"), null);
  });

  it("decodes URI-encoded params", () => {
    const m = matchRoute("/decks/:id/terms", "/decks/a%20b/terms");
    assert.ok(m);
    assert.equal(m!.params.id, "a b");
  });

  it("parses query strings without breaking matching", () => {
    const m = matchRoute("/nodes/:id", "/nodes/abc?foo=bar");
    assert.ok(m);
    assert.equal(m!.params.id, "abc");
    assert.equal(m!.query.get("foo"), "bar");
  });
});
