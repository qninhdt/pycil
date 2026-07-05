---
phase: 4
title: "FSRS Engine"
status: complete
priority: P1
effort: "1d"
dependencies: [1]
---

# Phase 4: FSRS Engine

## Overview
Pure FSRS-4.5 math in `packages/shared-py/shared/fsrs/` (no I/O), shared by API scheduling and worker grading. Binary Good/Again, hardcoded 17 default weights, mastery 0-100.

## Requirements
- Functional: `update(S, D, grade, elapsed_days) -> (S', D', interval_days)`; `recall(S, elapsed_days) -> R`; `mastery(S) -> int 0-100`; initial state for first review.
- Non-functional: no per-user fit, no review-log replay; deterministic; fully unit-tested against the design doc's worked examples.

## Architecture
Pure functions, no DB. Grade mapping: Đúng→Good(3), Sai→Again(1); Hard/Easy unused. **Verbatim port** of the FSRS-4.5 formulas from `docs/designs/fsrs-learning-engine.md` §4 — the design doc is the source of truth. Do NOT depend on `py-fsrs`: it ships FSRS-5/6 (19/21 params, not 17), is scheduler-shaped (`Card`/`Rating`/`review_card`), and won't yield our binary-only mapping + custom `mastery = round(100·S/(S+30))` + custom interval clamp. Tests pin behavior to the doc's worked-example table.

## Related Code Files
- Create: `packages/shared-py/shared/fsrs/{engine,recall,mastery,weights}.py`, `packages/shared-py/shared/fsrs/tests/`
- Reference (read-only): `docs/designs/fsrs-learning-engine.md` §2-§7, `main:apps/pycil-core/pycil_core/learning/{elo,intervals,mastery_levels}.py` (what's being replaced)

## Implementation Steps
1. `weights.py`: the 17 default FSRS-4.5 weights `w0..w16` as a frozen constant. Document source (Expertium technical explanation).
2. `recall.py`: `R(t, S) = (1 + (19/81)·t/S)^(-0.5)`.
3. `engine.py`: initial `S0 = w2 if correct else w0`; `D0 = clamp(w4 - exp(w5·(grade-1)) + 1, 1, 10)`. Success update `S' = S·(1 + exp(w8)·(11-D)·S^(-w9)·(exp(w10·(1-R))-1))`. Failure update `S' = min(S, w11·D^(-w12)·((S+1)^w13 - 1)·exp(w14·(1-R)))`. Difficulty mean-reversion (anti ease-hell). `interval = clamp(S, 30min→days, 365d)`.
4. `mastery.py`: `mastery = round(100·S/(S+30))`.
5. (No py-fsrs spike — verbatim port per Architecture. Implement per the doc's §4 formulas directly.)
6. Unit tests pinning doc's table: S=1→mastery 3, S=7→19, S=30→50, S=90→75, S=365→92; early-review (high R) → S barely grows; first correct → S0=w2.

## Success Criteria
- [ ] `mastery(S)` matches doc table exactly for S ∈ {1,7,30,90,365}
- [ ] Success/failure updates match doc formulas (unit-tested)
- [ ] Early review with high R yields near-zero S growth (anti-cram)
- [ ] No per-user fit, no optimizer, no review-log replay
- [ ] Shared module imports cleanly in both api + worker

## Risk Assessment
- py-fsrs API may not expose binary-only cleanly. Mitigation: fall back to verbatim formula port; either way tests pin behavior.
- Weight transcription errors. Mitigation: test-driven; assert worked examples from the design doc.
