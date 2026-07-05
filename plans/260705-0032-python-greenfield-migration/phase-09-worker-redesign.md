---
phase: 9
title: "Worker Redesign"
status: complete
priority: P1
effort: "1d"
dependencies: [4, 5, 8]
---

# Phase 9: Worker Redesign

## Overview
Slim the arq worker to three thin jobs that delegate to lexi-ai via the `LexiClient` port and publish completion to Centrifugo. lexi-ai persists dictionary content to ITS OWN database; the worker returns sense/question ids to pycil, never writes dictionary rows into pycil's DB.

## Requirements
- Functional: EXACTLY three jobs — `generate_word`, `generate_question`, `grade_answer`; each calls lexi via port, publishes result to the owner-scoped channel.
- Non-functional: no LLM/prompt/plugin code in the worker (lexi-ai owns it); worker keeps only arq bootstrap + dispatch + publish. Generation is single-writer (worker only). Paid lexi calls are idempotent across arq retries.

## Architecture
`apps/worker/pycil_worker/`: `main.py` (arq Worker + lifecycle hooks on startup/shutdown — NOT a job file), `jobs/` (THREE thin handlers only), `realtime.py` (publish via `shared/realtime`). Worker constructs an `InProcessLexiClient` and calls `await lexicon.init()` once at startup. Question gen + grading delegate to `lexicon.questions.*`. Dictionary persistence happens inside lexi-ai against its DB; worker updates only pycil learning tables (`user_sense_stats`, `review_log`, `responses`). **Generation runs in the worker ONLY** (single writer) — lexi's dedup guard is single-process; the API never generates.

## Related Code Files
- Create: `apps/worker/pyproject.toml`, `apps/worker/pycil_worker/{main,config,redis_helpers,realtime}.py`, `apps/worker/pycil_worker/jobs/{generate_word,generate_question,grade_answer}.py`
- Reference (read-only): current `apps/worker/worker/jobs/grade_answer.py:86` (is_terminal idempotency pattern), `:140-149` (verdict persist-back), `main.py:46` (max_tries=2); `packages/shared-py/shared/realtime/*` (Phase 8)
- Delete/omit: `worker/prompts/*`, `worker/llm/*`, `worker/schemas/*`, `worker/sanitize.py`, `shared/questions/*` (lexi-ai owns all of it); `tts_render.py`, `translate_definition.py` (moved to lexi-ai roadmap); NO `prewarm_questions.py` / `lifecycle.py` job files (brainstorm authorizes three jobs; lifecycle → `main.py`)

## Implementation Steps
1. `generate_word(word, owner_uid)`: `results = lexi.search(word)`; guard empty (`results[0]` → fall back to `lexi.generate(word_str)`); `entry = lexi.generate(results[0])` — lexi persists to its DB, returns `Entry` with sense ids. Publish `users:{owner_uid}:jobs:{job_id}` with sense ids (+ display). pycil stores no content. Idempotent on job id (skip if already terminal).
2. `generate_question(sense_ids, formats, n, owner_uid)`: `qs = lexi.questions.generate(entry, formats, n)` (via `lexicon.questions`, NOT `lexi.generate_questions`); lexi persists questions in its DB. Publish `users:{owner_uid}:jobs:{job_id}` with question ids/payloads.
3. `grade_answer(response_id, question_id, answer, owner_uid)`: **idempotency guard first** — if `is_terminal(response_id)` return `duplicate` (never re-bill LLM across arq's `max_tries=2`). Re-fetch authoritative question via `lexi.questions.get(question_id)` (never trust a passed payload); `score = lexi.questions.grade(question, answer)`; map `score.correct → FSRS Good/Again`; update `user_sense_stats` + `review_log` + **persist verdict to `responses`** (is_correct/grade_status/grade_score/grade_feedback) via learning service (Phase 6, per-(user,sense) lock); `commit_terminal(response_id)`; publish `users:{owner_uid}:grading:{response_id}`.
4. `main.py`: arq Worker settings (`max_tries=2`), Redis pool, construct `InProcessLexiClient` + `await lexicon.init()` at startup (lifecycle hook), register the three jobs. Generation is worker-only (single writer).
5. `realtime.py`: publish helper over `shared/realtime` owner-scoped channels/payloads.
6. Tests: each job with a fake LexiClient + fake Centrifugo; grade job updates pycil stats + writes review_log + persists verdict; **retry of a terminal grade job is a no-op (no second lexi.grade call)**; empty-search fallback; no job writes dictionary rows to pycil DB.

## Success Criteria
- [ ] EXACTLY three jobs (`generate_word`/`generate_question`/`grade_answer`) — no prewarm/lifecycle job files
- [ ] `generate_word` guards empty search; lexi persists to ITS db; worker publishes sense ids
- [ ] `generate_question`/`grade_answer` call `lexi.questions.*` (not `Lexicon` directly); `lexi.init()` run at startup
- [ ] `grade_answer` is idempotent across retries (terminal guard, no LLM double-bill), re-fetches question by id, persists verdict to `responses`
- [ ] Generation runs in worker only (single writer)
- [ ] Worker contains no prompt/LLM/plugin/sanitize code; no dictionary rows in pycil DB
- [ ] Jobs publish to owner-scoped Centrifugo channels

## Risk Assessment
- lexi generation latency holds the job. Mitigation: async job (off the request path); FE shows pending via Centrifugo.
- Grade job spans two DBs (read question from lexi, write stats to pycil). Mitigation: no distributed tx needed — idempotency guard + `commit_terminal` make retries safe; pycil write is the source of truth for learning state.
