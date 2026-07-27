# Phase 4 - pycil-core Adversarial Bug Hunt Report

Scope: auth+middleware, learning+ELO, jobs+streaming, billing+admin+compliance,
content services. Method: 6 parallel domain agents + controller adjudication.
Per review-audit-self-decision.md: a theoretical worry with no concrete failing
input is SUSPECTED, not a fix mandate; behavior-preserving fixes only.

Baseline core suite: 154 pass / 1 pre-existing fail (F7) / 9 skip.
After fixes: 158 pass / 1 pre-existing fail / 9 skip. Ruff clean.

## CONFIRMED bugs fixed

### C-scalar-1 (P2) - claim_username false 409 for self
- File: services/social_service.py:37 (import l.16)
- `select(User.id)` from sqlalchemy -> exec().first() is a Row, so
  `existing_id != user_id` (Row != UUID) is ALWAYS True -> a user re-saving
  the username they already own wrongly gets 409 username_taken.
- Fix: import select from sqlmodel (scalarizes single-col; multi-col Row attr
  access unaffected).
- verified by test test_claim_username_idempotent_for_self (+ taken-by-other still 409).

### C-scalar-2 (P2) - reverse_card distractors are Rows not strings
- File: services/reverse_card_service.py:82-83 (import l.17)
- `select(Definition.canonical_meaning)` from sqlalchemy -> .all() yields Rows;
  pool = [meaning for meaning in rows if meaning] holds Rows -> ReversePrompt
  .distractors gets wrong shape.
- Fix: import select from sqlmodel.
- verified by test test_reverse_prompts_distractors_are_strings.

### C-scalar-3 (P2) - me_extras follow-by-username binds a Row as UUID
- File: api/routes/me_extras.py:99 (import l.23)
- `select(User.id)` from sqlalchemy -> target_id is a Row passed as followee_id
  UUID into toggle_follow.
- Fix: import select from sqlmodel.

NOTE: the multi-column sqlalchemy.select sites (job_stream_service _load_owned_job,
chat.py deck_terms, me_extras admin audit, billing) are SAFE - empirically a
multi-col sqlalchemy.select().first() returns a Row with working attr access and
_mapping. Only single-col-consumed-as-scalar sites were bugs. Verified by sweep.

### D2 (P3) - upsert_subscription dropped updated_at=NOW() on conflict-update
- File: services/billing_service.py:86-93
- Pre-conversion DO UPDATE set clause had `updated_at = NOW()` (9f07149^ l.86);
  conversion dropped it. Column has no ORM onupdate=, and core
  on_conflict_do_update does not fire ORM onupdate -> updated_at frozen at
  insert time across every webhook update. Ordering correctness unaffected
  (uses last_event_at); audit/freshness only.
- Fix: add "updated_at": func.now() to set_ dict (+ import func).
- verified by test test_updated_at_advances_on_conflict_update.

### C1 (P2) - lock leak on commit failure in enqueue_generate_term
- File: services/job_service.py:100-141
- The fresh-job INSERTs + commit sat OUTSIDE the orphan-cleanup except (which
  only wrapped enqueue). A commit failure (unique violation/deadlock/conn drop)
  after acquiring lock:generate_term:{term_id} leaked it for the full 600s TTL
  -> term un-enrichable, downstream callers dedupe onto a rolled-back job ->
  404 on poll/SSE. "No lock leak" is a Phase 4 success criterion.
- Fix: wrap INSERTs+commit+enqueue in one try; on any failure rollback +
  redis.delete(lock_key) + best-effort mark job failed.
- verified by test test_commit_failure_releases_lock (+ existing orphan-cleanup green).

## SUSPECTED / escalated (NOT fixed - behavior-preserving scope)

These are real observations but either latent (unwired), pre-existing accepted
business behavior, or product-design calls. Documented, not silently changed.

- D1 (P2): per-user LLM spend cap (user_spend_service) has ZERO callers; worker
  writes a GLOBAL spend key, gate reads a per-user key that nothing increments.
  Per-user cap is non-functional. Likely deliberate v0.x scaffold; docstring is
  misleading. ESCALATE: wire it or delete the dead module + fix docstring.
- D3 (P3): admin_audit_service.record() has zero callers; admin revoke_tokens
  performs no audit write -> GDPR "account changes" surface empty. ESCALATE.
- D4 (P3): per-user spend key uses local date.today() vs global UTC; latent
  until D1 wired.
- E1 (P1-if-routed): deck_search_service.search binds user_id but never
  references it in WHERE -> reads any deck's terms. Currently NO caller (latent).
  ESCALATE before routing.
- E2/E3/E5 (P2-if-routed): classroom_service.assign_deck no deck-ownership
  check; list_assigned malformed join; join_with_code TOCTOU on max_students.
  classroom_service is unrouted (latent). ESCALATE before routing.
- E4: definition_sense_service.set_primary mutates global primary sense, no
  authz; unrouted. ESCALATE before routing.
- B1 (P2): learning ELO elo_at_start snapshotted at session start, not re-read
  at commit -> concurrent same-definition sessions can lose-update. Depends on
  whether concurrent multi-session study of the same deck is in v1 scope.
  ESCALATE (product call).
- B2/B4 (P3): user-ELO E computed vs constant 1000 (Question.elo not threaded);
  realized_score always 1.0 from submit path (monotonic ELO). Likely deliberate
  v1 simplification; ESCALATE as product call.
- B1 body_size multi-chunk truncation (P2): replay_receive emitted only the
  first buffered chunk with more_body=False. Fix was already staged
  (uncommitted) before this session; it coalesces chunks into one replay
  message. RETAINED.

## REFUTED (do not re-investigate)
- Auth core solid: exp enforced, token_version checked per request (no cache),
  HS256 pinned, malformed claims -> 401. CSRF subdomain/port/case bypass refuted.
- IDOR parity: 30 converted mutations, 0 dropped tenancy predicates (Phase 2).
- Billing webhook replay/out-of-order: dedup PK + row-value tiebreak intact;
  COALESCE-direction N/A (plain excluded.x).
- redis.aclose() does NOT disconnect shared pool (auto_close_connection_pool=False).
- Rate-limit EXPIRE set only on n==1 (no sliding-window bug).
