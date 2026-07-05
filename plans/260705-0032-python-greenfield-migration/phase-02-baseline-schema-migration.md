---
phase: 2
title: "Baseline Schema & Migration"
status: complete
priority: P1
effort: "1.5d"
dependencies: [1]
---

# Phase 2: Baseline Schema & Migration

## Overview
Author pycil's greenfield SQLModel schema + a single Alembic baseline. pycil owns ONLY auth + hierarchy + learning-state tables. Dictionary content (words/senses/questions) lives in lexi-ai's SEPARATE database — pycil references `sense_id`/`word_id` as opaque ids, never stores content, never FKs across.

## Requirements
- Functional: `alembic upgrade head` builds pycil's schema on an empty Postgres DB.
- Non-functional: no dictionary tables; no billing/social/admin/gamification; no cross-DB FK.

## Architecture
Two Postgres databases on one node: pycil's DB (this migration) + lexi-ai's DB (its own `create_all`). Postgres forbids cross-database JOINs → boundary enforced by the engine. `sense_id`/`word_id` in pycil tables are plain bigints (opaque refs), NOT foreign keys. Hierarchy = adjacency list `nodes.parent_node_id` + `REFERENCE` reusing `target_node_id`.

## Related Code Files
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_baseline.py`
- Create: `apps/api/pycil/auth/models.py` (User — no Session table, auth is stateless JWT), `content/models.py` (DeckSense — membership only; NO DeckWord), `hierarchy/models.py` (Node, FolderAttributes, DeckAttributes, UserNode), `learning/models.py` (UserSenseStats, ReviewLog, Response — NO UserDailySnapshot)
- Reference (read-only): `main:apps/pycil-core/alembic/versions/*` (schema intent), `apps/api/ent/migrations/20260612161324_initial.sql` (Go schema for column parity)
- Explicitly NOT created: no `words`/`senses`/`word_aliases`/`entry_links`/`questions` tables (lexi-ai owns these in its DB)

## Implementation Steps
1. `users`: id uuid, email, name, image, role, banned_at, token_version, timestamps. NO `sessions` table — auth is stateless JWT; revocation via `token_version` bump, refresh via `/auth/refresh` reissue.
2. `nodes`: id uuid, author_id, type (FOLDER|DECK|REFERENCE), parent_node_id (adjacency), target_node_id (REFERENCE only), name, description, visibility, sense_count (denormalized), likes/forks, timestamps + soft delete. `folder_attributes(node_id, subfolder_count)`, `deck_attributes(node_id, settings jsonb)`, `user_nodes(user_id, node_id, is_starred, is_pinned)`.
3. Membership (opaque ref, no FK to lexi): `deck_senses(id, node_id, sense_id bigint, position)` UNIQUE(node_id, sense_id). NO `deck_words` — `sense_id` is the sole learnable unit; no phase reads word-level membership.
4. `user_sense_stats`: user_id + sense_id (bigint, opaque) PK, stability float, difficulty float, mastery int (0-100), interval_days float, last_review_date, next_review_date, review_count, status, buried_until, lapse_count. NO mastery_score, NO mastery_level, NO FK on sense_id.
5. `review_log`: bigint id, user_id, sense_id (opaque), node_id nullable, stability_before/after, mastery_before/after, grade smallint, reviewed_at. **Plain table** + BTREE(user_id, reviewed_at). NO partitioning, NO BRIN, NO snapshot — MVP scale is thousands of rows (design doc scopes partitioning to 100M+). Add partitioning via additive migration when row counts warrant it.
6. NO `user_daily_snapshot` table — global/trend stats computed on read from `review_log` (design §7 says compute-on-read is cheap at this scale). Add snapshot table later if dashboard load warrants.
7. `responses`: the session answer record + async grading verdict persist-back. Columns: id, user_id, sense_id (opaque), question_id (opaque lexi id), is_correct, grade_status ('pending'|'graded'), grade_score float null, grade_feedback text null, answered_at, graded_at null. Verdict persisted here so a missed Centrifugo push is recoverable via refetch (B5). Question CONTENT is lexi-ai's.
8. Configure `alembic/env.py` for async engine + SQLModel metadata (pycil metadata only). Author `0001_baseline.py` — plain tables, no partition DDL.
9. Verify: `alembic upgrade head` on fresh pycil DB; `\dt` shows only pycil tables (no words/senses/questions); `alembic downgrade base` clean.

## Success Criteria
- [ ] `alembic upgrade head` builds pycil schema on empty Postgres DB
- [ ] NO `words`/`senses`/`word_aliases`/`entry_links`/`questions` tables in pycil DB
- [ ] `sense_id`/`word_id` are plain bigints with NO cross-DB FK
- [ ] No billing/social/admin/gamification/stripe/`user_definition_stat` tables
- [ ] `user_sense_stats` has FSRS columns, no ELO/mastery_level
- [ ] `review_log` is a plain table + BTREE(user_id, reviewed_at); NO partitioning/BRIN/snapshot
- [ ] `nodes` supports FOLDER/DECK/REFERENCE via adjacency list

## Risk Assessment
- `review_log` is a plain table for MVP (no partitioning) — add partitioning via an additive migration only when row counts warrant it (design doc scopes partitioning to 100M+ rows).
- Opaque `sense_id` risks orphan refs (lexi sense deleted). Mitigation: lexi-ai senses are append-only/lazy (rarely deleted); pycil tolerates missing sense on read (skip + log), no FK needed.
