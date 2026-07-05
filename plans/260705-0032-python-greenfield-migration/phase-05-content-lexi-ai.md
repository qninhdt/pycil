---
phase: 5
title: "Content & Lexi-AI"
status: complete
priority: P1
effort: "1.5d"
dependencies: [1, 2]
---

# Phase 5: Content & Lexi-AI

## Overview
Deck membership CRUD + the `LexiClient` port that isolates all dictionary/question access behind an interface. pycil stores NO dictionary content — it references `sense_id`/`word_id` opaquely and reads content through the client. MVP ships an in-process adapter over the lexi-ai library; the seam allows a later gRPC swap.

## Requirements
- Functional: deck CRUD; `POST /words` triggers lexi-ai generation (enqueue); read paths resolve sense content via the client.
- Non-functional: no dictionary tables/CRUD in pycil; all lexi access goes through the port (no direct `Lexicon` calls outside the adapter).

## Architecture
`content/` domain owns: `lexi_port.py` (Protocol), `lexi_inprocess.py` (wraps `~/projects/lexi-ai` Lexicon for MVP), `service.py` (deck membership + trigger generation), `router.py`. lexi-ai persists dictionary rows into ITS OWN database; pycil only records `deck_senses` membership + reads `Entry`/`SenseView` through the client. All node/deck routes gated by `require_node_access` (owner-or-public read, owner-only write). Generation is async (enqueue → worker → lexi persists → Centrifugo).

**lexi-ai gap:** the port needs `get_senses(sense_ids) -> list[SenseView]`, which lexi-ai does NOT expose today (`Lexicon.get()` takes a *word_id*, not sense_id — `api.py:211`). This method must be ADDED to lexi-ai first (see Phase 5 step 0 + note in `~/projects/lexi-ai/notes.md`). `generate`/`grade`/question-gen live on `Lexicon.questions` (the lazy `QuestionEngine`), not on `Lexicon` directly.

## Related Code Files
- Create: `apps/api/pycil/content/{lexi_port,lexi_inprocess,service,router,schemas}.py`
- Modify: `apps/api/pycil/content/models.py` (DeckSense membership only — Phase 2; no DeckWord)
- Modify (lexi-ai): `~/projects/lexi-ai/lexi_ai/api.py` (+ `persistence/repository.py`) — add `get_senses(sense_ids)`
- Reference (read-only): `~/projects/lexi-ai/lexi_ai/api.py:81` (`init`), `:142` (`search`), `:211` (`get`=word_id), `:87` (`questions` property → `QuestionEngine`), `questions/engine.py:41` (`generate`), `:66` (`grade`), `:79` (`get(question_id)`); `read_models.py` (Entry/SenseView/Question/Score); `config.py:28` (`cambridge_db_path`)

## Implementation Steps
0. **(lexi-ai first)** Add `Lexicon.get_senses(sense_ids: list[int]) -> list[SenseView]` to `~/projects/lexi-ai/lexi_ai/api.py` (+ repository query joining `senses` by id, assembling `SenseView` with `cefr_level`/`definition`/`examples`). This is the batch content-resolution method pycil depends on; lexi has no sense-keyed lookup today.
1. `lexi_port.py`: `LexiClient` Protocol — `search(q) -> list[SearchResult]`, `generate(source) -> Entry`, `get_senses(sense_ids) -> list[SenseView]`, `generate_questions(entry, formats, n) -> list[Question]`, `grade(question, answer) -> Score`, `get_question(qid) -> Question`. Types are lexi read models (imported, not redefined).
2. `lexi_inprocess.py`: `InProcessLexiClient` delegating to a `Lexicon` instance (its own DB_URL → lexi-ai's DB). `generate_questions`/`grade`/`get_question` delegate to `lexicon.questions.*` (the `QuestionEngine`), NOT `lexicon` directly. Async, connection-managed. Requires `await lexicon.init()` at startup (Phase 11) + the Cambridge SQLite file provisioned (see step 6).
3. `service.py`: `request_word(norm)` → enqueue `generate_word` (worker calls lexi via port; generation is single-writer in the worker). Deck membership: create/rename/delete deck node (all gated by `require_node_access`, owner-only write); `add_sense(node_id, sense_id)`, `remove_sense`, `reorder` — write `deck_senses` (opaque id, no content). `resolve_senses(ids)` → `client.get_senses` for display.
4. `router.py`: `/words` (POST = trigger generation), `/decks` CRUD, `/decks/{id}/senses` (membership), `/decks/{id}/items` (resolve content via client). Every route gated by `require_node_access` (owner-or-public read, owner-only write) — see Phase 7.
5. `schemas.py`: DTOs use `senseId` (opaque) + content fields populated from client responses, not pycil rows.
6. **Cambridge provisioning:** lexi `search()` needs the read-only Cambridge SQLite file (`config.py:28` `cambridge_db_path`). Ship/mount it + set `LEXI_CAMBRIDGE_DB_PATH` (Phase 1 compose). Guard `search(word)[0]` against empty results — fall back to `lexi.generate(word_str)` (custom-string path) when no ref found.
7. Tests: port contract (fake LexiClient), deck membership CRUD + ownership rejection, `resolve_senses` calls client not DB, enqueue path (fake arq), empty-search guard. No test asserts pycil stores sense content.

## Success Criteria
- [ ] `Lexicon.get_senses(sense_ids)` added to lexi-ai and returns SenseView list
- [ ] `LexiClient` port defined; `InProcessLexiClient` delegates (questions via `lexicon.questions`)
- [ ] All lexi access goes through the port (grep: no `Lexicon(` outside `lexi_inprocess.py`)
- [ ] Deck membership CRUD writes only `deck_senses` (opaque ids); every route gated by `require_node_access`
- [ ] `POST /words` enqueues `generate_word`; pycil persists no dictionary content
- [ ] `/decks/{id}/items` resolves sense content via `get_senses`
- [ ] Cambridge SQLite provisioned + `search()[0]` empty-guarded
- [ ] pycil DB has no words/senses/questions rows

## Risk Assessment
- `get_senses` must be built in lexi-ai before pycil depends on it. Mitigation: Phase 5 step 0 + note in lexi-ai notes.md; it is a straightforward sense-by-id query + SenseView assembly.
- Content resolution latency (per-request client calls). Mitigation: batch `get_senses`; optional in-memory content map (design §7); acceptable for MVP.
