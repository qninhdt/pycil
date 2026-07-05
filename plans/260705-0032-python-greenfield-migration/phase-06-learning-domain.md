---
phase: 6
title: "Learning Domain"
status: complete
priority: P1
effort: "2d"
dependencies: [2, 4, 5]
---

# Phase 6: Learning Domain

## Overview
Study sessions, the FSRS-backed answer flow, the asymmetric question router, and the always-non-empty session queue. Consumes the shared FSRS engine (Phase 4) and content (Phase 5).

## Requirements
- Functional: `/sessions` start; `/questions/next` returns a question + `recommended_type`; `/answers` takes `question_id` + answer, records outcome, updates `user_sense_stats`, writes `review_log`.
- Non-functional: queue never empty; new/review ratio configurable per-deck/user; grading verdict comes ENTIRELY from lexi-ai (server re-fetches the authoritative question by id — never trusts a client-supplied question payload); pycil only maps `Score.correct` → Good/Again.

## Architecture
`learning/` domain: `session.py` (queue build), `router_question.py` (mastery-cap table), `grading.py` (lexi `Score` → FSRS grade + `GradeResponse` mapping), `fsrs.py` wrapper over `shared/fsrs`, `mastery.py`. Session queue ranks all senses by R ascending (due first, upcoming still included), mixes new per configured ratio.

**pycil question types map to lexi-ai's four real formats** (lexi has no `mcq/fill/write`): `mcq` → `definition_mcq` + `contextual_mcq`; `fill` → `cloze`; `write` → `use_in_sentence` (`lexi_ai/constants.py:111`, `questions/formats.py:273`). The router requests only valid lexi format ids. pycil does NO grading itself — the verdict always comes from `lexi.grade()` (rule-based for mcq/cloze, LLM-judge for use_in_sentence), which dispatches to the format plugin. `Score` → `GradeResponse` mapping: `correct→is_correct`, `kind→grade_status`, `score→grade_score`, `feedback→grade_feedback`.

## Related Code Files
- Create: `apps/api/pycil/learning/{router,service,session,router_question,grading,schemas}.py`, `learning/fsrs.py` (thin wrapper), `learning/mastery.py`
- Modify: `apps/api/pycil/learning/models.py` (Phase 2)
- Reference (read-only): `docs/designs/fsrs-learning-engine.md` §3,§6,§7; `main:apps/pycil-core/pycil_core/learning/term_selection.py`, `services/answer_grading_service.py`

## Implementation Steps
1. `session.py`: build queue — rank senses in scope by `R(S, elapsed)` ascending; include upcoming (R high) so queue never empties; interleave new senses per ratio read from `deck_attributes.settings` (fallback 2 new / 10 review).
2. `router_question.py`: mastery→cap table (`<30`→mcq 100%; `30-65`→cap1 cloze 80%/mcq 20%; `>65`→cap2 use_in_sentence 70%/cloze 20%/mcq 10%); sample one type ≤ cap; map to lexi format id; return `recommended_type` to FE.
3. `grading.py`: verdict ALWAYS from `lexi.grade(question, answer)` (server re-fetches question by id first — never trust client payload). Map `Score.correct` → Good(3)/Again(1); build `GradeResponse` from `Score` (kind→grade_status, score→grade_score, feedback→grade_feedback). No pycil-side threshold/inline grading. First attempt per sense per session is the only one that touches S; re-drills are relearning steps.
4. `service.py`: `answer(question_id, answer)` → re-fetch authoritative question via `LexiClient.get_question(question_id)`, grade via lexi, then under `SELECT ... FOR UPDATE` on `user_sense_stats` row (per-(user,sense) lock): load stats, guard first-attempt-in-session marker, call `shared.fsrs.update`, upsert `user_sense_stats`, insert `review_log`, persist verdict to `responses` (all one tx). After commit: publish grading result via Centrifugo. NO L2 cache bust (L1-only per Phase 7).
5. `router.py`: `/sessions` (start/resume), `/questions/next`, `/answers` (takes `question_id` + answer, NOT a question payload). All gated by `require_node_access` for the session's deck.
6. `schemas.py`: session/question/answer DTOs, sense-based.
7. Tests: queue non-empty when nothing due; ratio honored; cap never exceeded; answer updates S/D/mastery + writes review_log; first-attempt-only S update; **`/answers` rejects a client-supplied question payload and grades only the re-fetched question; concurrent double-answer for same (user,sense) applies ONE first-attempt update (lock test)**.

## Success Criteria
- [ ] `/questions/next` returns a valid lexi format id respecting mastery cap + `recommended_type`
- [ ] Queue non-empty even when no card is due
- [ ] New/review ratio read from deck/user config, default applied when unset
- [ ] `/answers` takes `question_id`, re-fetches authoritative question server-side, grades via lexi (never client payload)
- [ ] `/answers` updates `user_sense_stats` via FSRS + writes `review_log` + persists verdict to `responses` in one tx under per-(user,sense) lock
- [ ] Only first attempt per sense per session mutates S (holds under concurrent answers)
- [ ] pycil contains no grading-threshold logic (lexi-ai owns verdict)

## Risk Assessment
- Ratio config source ambiguity (deck vs user). Mitigation: deck setting overrides user default; both optional, hard fallback constant.
- R-ranking cost over large scope. Mitigation: cap scope to deck/folder set (Phase 7 provides the sense set); index next_review_date.
- Deferred WRITE grade races first-attempt bookkeeping. Mitigation: `SELECT ... FOR UPDATE` on the `user_sense_stats` row serializes per-(user,sense) FSRS updates; first-attempt marker set atomically in the same tx.
