---
phase: 7
title: "Hierarchy & Stats"
status: complete
priority: P1
effort: "2d"
dependencies: [2, 5]
---

# Phase 7: Hierarchy & Stats

## Overview
Folder/deck/REFERENCE tree + per-user mastery statistics per the hierarchy design doc. All stat queries stay INSIDE pycil's DB (`deck_senses` + `user_sense_stats`); sense content (CEFR) resolves via the LexiClient, never a cross-DB JOIN.

## Requirements
- Functional: node CRUD (folder/deck/reference); `GET /folders/{id}/stats` → {total, learned, mastered, avg_mastery}; item list; weakest-N; CEFR distribution; global totals. Every route ownership-gated.
- Non-functional: uncached folder stats < 50ms on a 2k-sense folder (design's own numbers put uncached at ~10-20ms); **L1 cache only** for MVP (user-agnostic def-set); no per-user L2, no review-coupled invalidation until load measured.

## Architecture
`hierarchy/` domain: `access.py` (`require_node_access` dependency — owner-or-public read, owner-only write, soft-delete filter), `subtree.py` (Stage-1 recursive CTE resolving folder → sense-id set, REFERENCE leaves expand to target deck), `stats.py` (Stage-2 user overlay via `user_sense_stats`), `cache.py` (**L1 only**: user-agnostic def-set + CEFR counts). CEFR distribution: resolve sense ids → CEFR via `LexiClient.get_senses` (or in-memory content map), bucket in Python — NOT a SQL JOIN to lexi tables (separate DB). **L2 per-user stats cache DEFERRED** — uncached already meets the <50ms target; add later on measured load. No review→bust coupling.

## Related Code Files
- Create: `apps/api/pycil/hierarchy/{router,service,subtree,stats,cache,schemas}.py`
- Modify: `apps/api/pycil/hierarchy/models.py` (Node, attributes, UserNode — Phase 2)
- Reference (read-only): `docs/designs/vocabulary-hierarchy-stats-architecture.md` §7, §8

## Implementation Steps
1. `subtree.py`: recursive CTE over `nodes.parent_node_id` resolving a folder to its DECK set; REFERENCE leaves contribute `target_node_id`'s deck. Return DISTINCT `sense_id` set from `deck_senses`. All within pycil DB.
2. `stats.py` Query 1: LEFT JOIN the sense-id set against `user_sense_stats` for the user → total (set size), learned (stat rows), mastered (mastery ≥ threshold param), avg_mastery. JOIN against CTE/temp-set, never `= ANY(bigarray)` (doc §10).
3. `stats.py` Query 3 (weakest-N): top-N by mastery asc over user's learned subset. Query global totals: aggregate `user_sense_stats` for user.
4. CEFR distribution: take Stage-1 sense-id set → `LexiClient.get_senses(ids)` (or in-memory content map) → bucket by `cefr_level` in Python. Cache alongside L1.
5. `cache.py`: **L1 only** — `node:{id}:defset` (sense-id set + CEFR counts), busted on structural edits (walk ancestors via parent_node_id, O(depth)). NO L2 per-user cache, NO review-coupled bust for MVP (uncached stats meet the <50ms target). Add L2 later behind measured load.
5b. History graph (`GET /folders/{id}/history`, `/me/stats` trend): computed on read from `review_log` (carry-last-value-forward per day bucket in Python). No snapshot table.
6. `access.py`: `require_node_access(node_id, user, mode)` FastAPI dependency — resolve node, check `author_id == user` (write) or `author_id == user OR visibility == PUBLIC` (read), filter `deleted_at IS NULL`. Port semantics from `apps/api/internal/store/node_access_store.go:18-47`.
7. `router.py`: `/nodes` CRUD (folder/deck/reference create, move, soft-delete), `/folders/{id}/stats`, `/folders/{id}/items`, `/folders/{id}/weakest`, `/folders/{id}/history`, `/me/stats`. **Every route depends on `require_node_access`** (owner-only write, owner-or-public read); `/me/stats` scoped to the caller.
8. REFERENCE creation: validate target is a DECK; leaf (no children); cycle-free by construction.
9. Tests: subtree resolve with nested folders + reference; stats correctness (learned/mastered/avg); CEFR bucketing via fake LexiClient; L1 invalidation on structural edit; mastered-threshold parameterized; **IDOR: user A cannot read/write user B's private node (403); public node readable, not writable, by non-owner**.

## Success Criteria
- [ ] Every node/folder/deck/stats route gated by `require_node_access` (IDOR test passes)
- [ ] Nested folders + deck + REFERENCE create/resolve correctly
- [ ] `GET /folders/{id}/stats` returns {total, learned, mastered, avg_mastery}
- [ ] Uncached stats < 50ms on 2k-sense folder; L1 hit on second call
- [ ] CEFR distribution resolved via `get_senses`, NOT a cross-DB JOIN
- [ ] Structural edit busts ancestor L1 keys (O(depth)); NO L2 / no review-coupled bust
- [ ] History computed from `review_log` on read (no snapshot table)
- [ ] REFERENCE cannot target a folder (deck-only) and cannot cycle

## Risk Assessment
- CEFR resolution per stats call adds client round-trips. Mitigation: in-memory content map (design §7.3) refreshed on change; or cache CEFR counts in L1 (user-agnostic, rarely changes).
- Recursive CTE depth. Mitigation: real depth < 20; index `parent_node_id`; cap + guard if folder-references land later.
- Missing ownership check = systemic IDOR (the single largest gap vs the old Go code). Mitigation: `require_node_access` is a hard dependency on every route; IDOR test is a success criterion.
