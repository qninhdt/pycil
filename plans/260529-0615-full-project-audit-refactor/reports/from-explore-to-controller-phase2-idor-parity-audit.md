# Phase 2 IDOR Parity Audit — raw SQL → SQLModel (commit 9f07149)

Goal: prove the conversion dropped NO tenancy/authorization predicate on mutating queries.
Method: `git show 9f07149^:<file>` (old raw SQL) vs `git show 9f07149:<file>` (new ORM); compared WHERE predicate SETS; traced upstream ownership for id-only canonical-table writes.

## DROPPED-PREDICATE (IDOR) findings

**NONE.** No mutating statement lost a user_id / created_by / author_id / ownership predicate.

## Parity table

| file:line | old WHERE | new .where(...) | verdict | evidence |
|---|---|---|---|---|
| node_service.py:182 (update Node) | `id=:id` | `Node.id==node_id` | UPSTREAM-OK | `_ensure_owner` (author_id check) at node_service.py:173 before mutate |
| node_service.py:190 (delete Node) | `id=:id` | `Node.id==node_id` | UPSTREAM-OK | `_ensure_owner` at node_service.py:189 |
| node_service.py:160 (FolderAttribute counter) | `node_id=:id` (parent) | `FolderAttribute.node_id==parent_node_id` | UPSTREAM-OK | parent gated by `_ensure_owner` at create_node:140; counter table |
| share_link_service.py:56 (revoke) | `id=:lid AND created_by=:uid AND revoked_at IS NULL` | `id==link_id, created_by==user_id, revoked_at.is_(None)` | PARITY-OK | full ownership preserved |
| definition_comments_service.py:82 (soft_delete) | `id=:id AND (author_id=:a OR :a IN (admins))` | `id==comment_id, deleted_at.is_(None) [+ author_id==actor_id if not is_admin]` | PARITY-OK (caveat) | author path identical; **admin check externalized to caller bool `is_admin` (default False=safe)**; no caller wired yet |
| definition_sense_service.py:98 (set_primary) | `term_id=:tid` | `Definition.term_id==term_id` | PARITY-OK | identical; `definitions` canonical/shared (no user col); no user predicate in either |
| term_batch_service.py:161 (Term.source) | `value=ANY(:vals) AND source='manual'` | `Term.value.in_(...), Term.source=='manual'` | PARITY-OK | identical; `terms` canonical (no user col); upstream rate+budget by user_id |
| social_service.py:40 (User username) | `id=:id` | `User.id==user_id` | PARITY-OK | self-update |
| social_service.py:61 (delete Follow) | `follower_id=:f AND followee_id=:t` | both | PARITY-OK | identical |
| social_service.py:90 (delete DeckLike) | `user_id=:u AND deck_id=:d` | both | PARITY-OK | identical |
| social_service.py:96/111/120 (Node likes/forks counters) | `id=:d` | `Node.id==deck_id` | PARITY-OK | id-only counters in both (shared deck counter, by design) |
| notification_service.py:82 (mark_read) | `user_id=:uid AND id=ANY(...) AND read_at IS NULL` | `user_id==user_id, id.in_(ids), read_at.is_(None)` | PARITY-OK | identical |
| cefr_threshold_service.py:55 (User study_settings) | `id=:id` | `User.id==user_id` | PARITY-OK | self-update |
| billing_service.py:44 (User stripe_customer_id) | `id=:uid` | `User.id==user_id` | PARITY-OK | self-update |
| saved_search_service.py:90 (update) | `id=:id AND user_id=:u` | `id==search_id, user_id==user_id` | PARITY-OK | identical |
| saved_search_service.py:101 (delete) | `id=:id AND user_id=:u` | both | PARITY-OK | identical |
| definition_overrides_service.py:57 (delete) | `user_id=:u AND term_id=:t` | both | PARITY-OK | identical |
| push_notification_service.py:58 (delete by endpoint) | `user_id=:u AND endpoint=:ep` | both | PARITY-OK | identical |
| push_notification_service.py:116 (delete by id) | `id=:id` (loop over user's subs) | `id==s.id` (loop over select where user_id==user_id @:96) | PARITY-OK | iterates user-scoped set in both |
| term_status_service.py:34 (set_status) | `user_id=:u AND term_id=:t` | both | PARITY-OK | identical |
| term_status_service.py:52 (bury/suspend) | `user_id=:u AND term_id=:t` | both | PARITY-OK | identical |
| term_status_service.py:75 (reactivate_buried, cron) | `status='buried' AND buried_until IS NOT NULL AND buried_until<=CURRENT_DATE` | three matching preds | PARITY-OK | global cron sweep, no user scope in either |
| daily_goal_service.py:42 (User) | `id=:id` | `User.id==user_id` | PARITY-OK | self-update |
| user_service.py:85 (update User) | `id=:uid` | `User.id==user_id` | PARITY-OK | self-update |
| user_service.py:100 (soft_delete_user) | `id=:uid AND deleted_at IS NULL` | `User.id==user_id, deleted_at.is_(None)` | PARITY-OK | identical |
| user_service.py:115 (hard_delete_expired, cron) | `deleted_at IS NOT NULL AND deleted_at < NOW()-14d` | `deleted_at.is_not(None), deleted_at < (now-14d)` | PARITY-OK | identical; 14-day cutoff preserved |
| term_notes_service.py:52 (delete) | `user_id=:u AND term_id=:t` | both | PARITY-OK | identical |
| elo_calibration_service.py:62 (Question.elo) | `id=:id` | `Question.id==r.id` | PARITY-OK | id-only in both; `questions` canonical/system-generated; system batch |

## Summary

- **30 mutating statements audited.**
- **30 PARITY-OK / UPSTREAM-OK.**
- **0 real IDOR risks** (no dropped tenancy/ownership predicate).
- Node update/delete (id-only) confirmed safe: `_ensure_owner` (author_id) runs before every mutate.
- Canonical shared tables (`terms`, `definitions`, `questions`, deck counters) correctly id-only in BOTH versions — no per-user predicate existed to drop.

## Unresolved questions / notes

1. **definition_comments_service.soft_delete admin-check externalization** (NOT an IDOR now, default-safe): old SQL enforced admin via DB subquery `:a IN (SELECT id FROM users WHERE is_admin)`. New code moves this to caller-supplied `is_admin: bool = False`. When the future route caller wires it, it MUST verify admin role server-side; passing an unverified client-controlled `is_admin=True` would become IDOR. Default `False` keeps author-scoping. Flag for Phase 4 when the comments route is wired (no caller exists in this WIP checkpoint).
2. `definition_sense_service.set_primary` and `definition_comments_service.soft_delete` have NO callers in this checkpoint (services unwired) — parity verified at statement level only; route-layer authz not yet testable.
