# Phase 2 - Conversion Parity Audit Report

Goal: prove the ~200 raw-SQL->SQLModel converted call sites (checkpoint 9f07149)
preserve exact behavior. Method: diff each hunk old (9f07149^) vs new; classify
pattern; skeptic pass for old != new; verdict EQUIVALENT or REGRESSION + repro.

## Summary verdict

- IDOR / tenancy-predicate parity: CLEAN. 30 mutating statements audited old-vs-new,
  0 dropped user_id/created_by/author_id predicates. Report:
  from-explore-to-controller-phase2-idor-parity-audit.md.
- RETURNING unwrap (isinstance(row, tuple) hack): FIXED (F14). Empirically proved
  .returning(col) yields a Row not a tuple; replaced with positional row[0].
- .first()/.one() null semantics: audited; no .one() introduced where original SQL
  tolerated 0 rows.
- NEW conversion-parity REGRESSION CLASS found + fixed: the `select` scalarization
  bug (see below). This is the single largest parity defect the conversion shipped.

## The scalarization regression class (CONFIRMED + fixed)

Root cause: the conversion replaced `text(...)` with `session.exec(select(...))` but
in many files imported `select` from `sqlalchemy` rather than `sqlmodel`. SQLModel's
AsyncSession.exec() auto-scalarizes ONLY a sqlmodel.select. With sqlalchemy.select:

  - single-column select(Model.col).first()  -> Row (e.g. ('x',)), NOT the scalar
  - single-column select(Model.col).all()    -> list[Row], NOT list[scalar]
  - multi-column select(a, b).first()         -> Row with attr access (SAFE either way)

Empirically proven against live PG this session (probe table in worker-bug-hunt-report).

Pre-conversion raw SQL returned a Row whose attributes were accessed (row.status,
row.id), so single-col reads that are CONSUMED AS A SCALAR broke. Sites where the
result is only an existence check (`if not row`) or multi-col attr access were unharmed.

### Confirmed-broken-and-fixed sites (consumed as scalar)
- worker/jobs/lifecycle.py:is_terminal (W1, P1) - gate always False
- worker/jobs/generate_question.py (W3/W4, P2)
- services/social_service.py:claim_username (P2) - false 409
- services/reverse_card_service.py:build_prompts distractors (P2)
- api/routes/me_extras.py:follow-by-username (P2)

Fix in all: import select from sqlmodel. Behavior-preserving for multi-col sites
(Row attr access unchanged); restores scalar semantics for single-col sites.

### Audited-SAFE sqlalchemy.select sites (left as-is)
Multi-column selects with Row attr/_mapping access, OR single-col used only for
`if not row` existence on a never-null PK:
- job_stream_service._load_owned_job (multi-col Row attr)
- api/routes/chat.py deck_terms (multi-col, r.value/r.canonical_meaning)
- api/routes/me_extras.py admin audit (multi-col _mapping)
- billing_service (multi-col; .returning(user_id) only row-is-None tested)
- term_batch_service:109, translate_tts.py:27, question_regenerate.py:31
  (single-col select(Definition.id) used ONLY as `if not row` existence -> safe)
- cloze_service (scalar_subquery + multi-col labelled select)

## Other parity findings (fixed elsewhere)
- ON CONFLICT (term_id) on definitions references a constraint dropped by migration
  0012 -> changed to (term_id, sense_index). (W7; pre-existing, surfaced in Phase 5.)
- to_jsonb(:param::text) bind-param parse bug -> CAST(:param AS text). (W8;
  pre-existing raw-SQL, surfaced in Phase 5.)
- upsert_subscription dropped updated_at=NOW() on DO UPDATE -> restored. (D2;
  conversion regression.)

## F10 holdout (accepted, behavior-preserving)
data_export_service.py:79 + conftest test fixtures still use session.execute(text(...)).
SQLModel AsyncSession supports .execute; deprecation-warned only. Authz-clause parity
verified. Acceptable holdout.

## Conclusion
Conversion parity is now verified. The mechanical conversion's one systemic defect
(select import source -> scalarization) is fixed everywhere it caused a scalar-consumed
regression, and proven by former-failing tests. IDOR parity clean. No .one()-on-empty
regressions. Full DB-backed suite green (core 158 pass, worker 41 pass).
