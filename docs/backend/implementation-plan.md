# Backend completion and frontend-readiness implementation plan

Date: 2026-10-06. Status: **backend implemented; local verification and handoff**.

This is the consolidated execution plan for the remaining 2026-10-05 redesign and
the backend requirements accepted after reviewing the UI designs. The latest user
decisions override the original plan wherever they conflict. Creating this plan
did not itself authorize execution. The subsequent explicit user request authorized
backend implementation, but not commits, production migration, or deployment.

Current evidence: [verification record](verification.md), [implementation status](implementation-status.md),
[FE handoff](frontend-handoff.md), [exported OpenAPI](openapi.json) and
[performance procedure/evidence](operations/performance.md). Unchecked items below are
explicit external gates, not silent claims of production/FE completion.

## 1. Outcome and authority

### Deliverable

Complete the existing backend so FE can implement the agreed, reduced product scope
using real APIs and data, without per-card request fan-out or fabricated metrics.
Keep the existing architecture: Python API/worker, PostgreSQL, Redis, Clerk, native
Lexi content/question APIs, and the installed FSRS binding.

This is completion and bounded extension of the implemented foundation, not a new
tree, authorization system, scheduling algorithm, dictionary engine, or session service.

### Inputs and precedence

1. Latest user decisions in the conversation, including the explicit deferrals below.
2. This consolidated plan for remaining implementation and FE contracts.
3. Original design: `/tmp/opencode/2026-10-05-pycil-final-redesign-plan.md`, especially
   sections 9-14 and 17-23; its obsolete star/pin requirements are superseded.
4. Foundation checkpoint: `/tmp/opencode/2026-10-06-pycil-implementation-progress.md`.
5. UI/backend audit: `/tmp/opencode/2026-10-06-pycil-design-backend-readiness.md`.
6. Current source, schemas, migrations, and tests, not deleted legacy documentation.

The temporary source documents provide provenance. This repository document must
remain understandable without them. The audit covers 21 supplied images; screenshots
are not permission to implement features explicitly deferred later.

### Explicitly included

- Prepare selections **NEW / DUE / AUTO** and maximum-sense preferences.
- Batch-only atomic review submission with immutable original-result replay.
- Data-preserving progress/settings/receipt migrations and durable daily activity.
- Exact lightweight summaries, jointly budgeted card summaries, streaks and schedule.
- Library/scoped node search and public Discovery search using PostgreSQL FTS.
- Scope-wide sense text search, sorting, last-review metadata and source-deck provenance.
- Personalized dictionary progress/membership context and bounded batch lexical hydration.
- Profile **handle and bio**, and public-safe identity projections.
- Opaque scope/filter/order-bound cursors, strict limits, errors and authorization.
- Remaining assistant service alignment and removal of obsolete runtime contracts.
- Migration, correctness, query-count, cache, query-plan and representative load evidence.
- English OpenAPI/engineering/FE handoff documentation and executable contract scenarios.

### Explicitly excluded or deferred

- ALL node star/pin work: tables, routes, flags, Starred view, ordering and pin cursors.
- Sense star/difficult preferences or recommendations based on them.
- Node/word/membership tags and category taxonomy.
- Translation generation/storage/endpoints; retain existing saved language preference
  without pretending translated content is available.
- Country, geolocation, avatar uploads, or a comprehensive identity-sync subsystem.
- Import and TTS/audio infrastructure.
- A new normalized question-feedback subsystem; reuse generated answers/explanations
  and current typed grading/entitlements.
- Server learning sessions, per-question persistence, session timing/counts, answer
  accuracy telemetry, cross-device unfinished-session resume, or source-session attribution.
- Courses, learning paths, listening curriculum, recommendations, public popularity
  ranking or public learner-adoption metrics.
- Mastery, weakest-word features, raw public review history and CEFR dashboards.
  Native lexical CEFR metadata remains available.
- New persistent personal-summary caches, statistics cubes, search workers, outboxes,
  permission workers, external search services, or a rebuilt vendor wheel.
- Scaffolding or choosing a frontend framework in this backend-only repository.

## 2. Current baseline: preserve, do not redo

Inspected HEAD: `e79a53c`, on branch `dev`. The working tree also contains the managed
test runner/environment-name cleanup and uncommitted documentation. Treat the actual
working tree, not HEAD alone, as the implementation starting point.

| Area | Current state | Treatment |
| --- | --- | --- |
| Node identity/namespace | `Node` / `nodes`, `/v1/nodes`; collection aliases removed | Preserve |
| System spaces | Library/Personal/Published roots, server-controlled roles/spaces | Preserve |
| Placement publication | Confirmed canonical moves, retained reference option, live revocation | Preserve |
| Physical closure | Transactional `node_paths`; create/move/delete invariants | Preserve |
| Scope resolver | Viewer-local visitation, reference deduplication, work/time budgets | Extend for reusable scope projections and joint batches |
| Quotas | Depth 20; 1,000 senses/deck; 500 children; 2,000 owned nodes; 100,000 memberships | Preserve exact accounting and over-limit repair behavior |
| Metadata/editor split | Safe breadcrumbs, complete owner editor IDs, atomic full-state save | Preserve |
| Sense browsing | Paged ALL/NEW/DUE/NOT_YET_DUE, native batch previews | Extend query/sort/provenance/cursor |
| User provisioning/profile roots | Atomic roots; private root IDs and public Published ID | Preserve; add profile metadata |
| Whole-Library tracking | Reachable readable Library content, not every previously learned sense | Preserve |
| Vocabulary | Native search/content, asynchronous generation and status | Preserve; add host-side batch/context projections |
| Learning | `SenseMemory`, budget-derived AUTO prepare, one-sense receipts, combined progress/history | Replace remaining transitional contracts |
| Assistant | Renamed node tools, approval guards and packaged `system_prompt.txt` | Preserve protections; update remaining contracts/descriptions |
| Migration | Frozen `0001_baseline` and applied `0002_nodes_spaces_paths` | Never rewrite; append successors |
| Local tests | `make test-api` owns disposable PostgreSQL/Redis and cleanup | Use; do not reintroduce manual setup requirements |

Historical verification: foundation had 158 passing tests; the later managed-runner
and environment-name changes had 181 passing tests. These results do not verify any
feature proposed here. No scale/QPS/latency evidence has yet been established.

### Remaining-work traceability from the original plan

| Original item | Consolidated destination |
| --- | --- |
| Contract freeze and obsolete-field inventory | Phase 0 |
| `SenseMemory` rename, settings migration, batch receipts/activity | Phases 1-2 |
| Max senses and DUE/NEW/AUTO readiness-aware selection | Phase 3 |
| Exact summary, independent activity/streak/schedule, batch cards | Phase 4 |
| Final browsing and cursors | Phases 0 and 5 |
| Profile Published navigation and node FTS/Discovery | Phases 6 and 8; retain foundation navigation |
| Star/pin preferences and Starred view | Explicitly deferred, not unfinished work to sneak back in |
| Assistant alignment and obsolete runtime cleanup | Phase 9 |
| Migration/security/cache/error tests and EXPLAIN/load matrix | Phase 10 |
| Frontend integration | Phase 11 backend handoff; FE implementation needs a supplied target |

## 3. Invariants for every phase

1. One personal learning state per `(user_id, sense_id)` regardless of placement.
2. Organization/publication changes never reset progress, receipts or historical activity.
3. Authorization follows active system-root paths; `space` alone is not a grant.
4. Foreign public content is directly learnable; only Library reachability contributes
   to proactive Home counts. Star is not present in this release.
5. References are live, not copies or permanent access grants. Source-space rules remain.
6. Scope expansion is request/viewer-local, deduplicated and bounded. Reference hops
   do not consume physical depth. Oversize/timeout is an error, not partial success.
7. Prepare is read-only; it never creates progress, receipts, reservations or questions.
8. Accepted batch results, receipts and daily activity commit together.
9. Early HARD/GOOD/EASY practice leaves every existing FSRS state field unchanged;
   NEW, DUE and AGAIN results apply native scheduling.
10. No runtime compatibility aliases, dual body parsers or old preference fallbacks.
    Historical migrations/upgrade fixtures may intentionally name old schemas.
11. No FE per-card/per-sense automatic request fan-out; no corresponding SQL N+1 loops.
    Reference-frontier work may grow with bounded graph shape; do not promise O(1).
12. No inferred country, fake translations/audio, invented study minutes or session counts.
13. No paid provider calls in migration, correctness fixtures or benchmarks.
14. Preserve unrelated user changes and deleted root README/legacy documentation.

## 4. Final API inventory

The contracts in this table are implemented in the working tree. Module documentation
and the exported OpenAPI describe the current breaking contract.

| Operation | Planned contract |
| --- | --- |
| `GET /v1/me` | Existing self profile/root IDs plus handle, bio, joined date and safe learning-option metadata |
| `PATCH /v1/me/settings` | `max_sense_count`; reject old budget field; preserve other settings/entitlements |
| `PATCH /v1/me/profile` | Owner edits handle/bio only; no country or plan changes |
| `GET /v1/users/{user_id}` | Safe identity, handle/bio/joined date and Published root; no learning/private roots |
| `GET /v1/users/by-handle/{handle}` | Same safe profile lookup using canonical current handle |
| `GET /v1/nodes` | Bounded children with opaque cursor; optional `include=summary` inline card enrichment |
| Existing node create/detail/editor/save/delete | Preserve foundation semantics and strict no-visibility requests |
| `GET /v1/nodes/{id}/senses` | State/text query/sort/opaque cursor; optional examples/sources enrichment |
| `GET /v1/nodes/{id}/senses/{sense_id}/sources` | Bounded authorized provenance overflow, inside the same scope |
| `GET /v1/nodes/{id}/search` | Name/description FTS within Library/folder/reference scope |
| `GET /v1/discovery/nodes` | Published catalog browse/search; owner/type filters, cursor and optional summaries |
| `GET /v1/words/search` | Preserve native hit semantics; no global POS/count/paging promise added silently |
| `GET /v1/words/{word_id}` | Preserve public native full word content |
| `POST /v1/words/previews` | Bounded public word-group/sense/example hydration for modal/search cards |
| `GET /v1/me/words/{word_id}` | Viewer learning plus Library-scoped membership context for a word |
| `POST /v1/me/senses/context` | Bounded batch of the same viewer context for selected sense IDs |
| `GET /v1/me/senses/{sense_id}/decks` | Paged overflow for readable containing decks in the viewer's Library |
| Existing word-generation submit/status | Preserve current available-entry selection, retry and readiness statuses |
| `POST /v1/study/prepare` | Explicit node, NEW/DUE/AUTO, maximum senses; native bundles |
| `POST /v1/study/grade` | Existing native typed-grade result and Pro entitlement; no new feedback subsystem |
| `POST /v1/study/reviews` | Batch-only body plus UUID `Idempotency-Key` |
| `GET /v1/study/progress` | Lightweight exact scope summary and one `as_of` |
| `POST /v1/study/summaries` | Bounded joint summary request for cards from different pages/scopes |
| `GET /v1/study/activity` | Private date grid plus current/lifetime longest streak |
| `GET /v1/study/review-schedule` | Private current future due counts by date/scope |
| Existing assistant model/conversation/SSE operations | Preserve protocol/ownership/approval; align tools with new services |

Remove `GET /v1/study/history`. Do not add node/sense preference routes, Starred
routes, tag/translation/import/audio routes, or a normalized grade endpoint.

### Planned conservative limits

Retain existing policy limits and put added bounds in product policy, not new
deployment environment variables. These initial engineering defaults are plan
choices, not measured capacity claims:

| Bound | Initial target |
| --- | ---: |
| Generic metadata/sense/source page | Default 50, maximum 100 |
| Prepared questions | 100 |
| Questions per sense | 1-7; default 3 |
| Default maximum senses | 10 |
| Results in one review batch | 1-100 distinct senses |
| Explicit node-summary IDs | 50 distinct IDs |
| Logical membership work projected across unique summary scopes | 200,000 before per-scope sense deduplication |
| Physical scope expansion | Existing 10,000 nodes / 200,000 underlying memberships |
| Batch word hydration | 30 distinct word IDs / 500 returned senses |
| Viewer context IDs | 100 distinct senses |
| Inline sources/decks per sense | 5; overflow through explicit paging |
| Inline examples per sense | 2 stored native examples |
| Activity window | At most 366 inclusive dates |
| Review-schedule window | At most 30 inclusive dates |
| Node/sense query text | At most 200 characters |
| Encoded cursor | At most 2,048 characters |
| Handle / bio | 3-30 ASCII handle characters / 500 bio characters |

Malformed or excessive requests fail explicitly. A lexical batch above its hydration
bound returns an error, not a partially hydrated word labeled complete. Caller splits
the requested IDs. Error bounds must be documented and tested at equality and +1.

### Common pagination contract

- Replace raw `after_id`/`after`/assistant cursor pairs with `cursor` and bounded `limit`.
- Use strict, versioned opaque encoding of kind, viewer context, scope, normalized
  filters/order, seek tuple and `as_of` where time-sensitive filtering requires it.
- Encoding is not an authorization grant. Every request authorizes current scope/content;
  malformed or cross-scope/filter/user/kind cursors return 422 `invalid_cursor`.
- An unsigned opaque token may be used if all fields are validated and cannot bypass
  predicates; do not add a cursor-secret deployment variable without an actual need.
- Seek using token values, not a new permission lookup of the old anchor entity.
  Deleting/moving the anchor must not turn pagination into a private metadata lookup.
- Freeze state cutoff time within a sense-page traversal; never promise a persistent
  cross-request membership/progress snapshot. Mutations can reorder/change results;
  FE refreshes after edits/reviews. No list revision/session store is introduced.
- Deterministic tie-breakers, explicit null placement, no deep OFFSET.
- No exact global result count by default. Return `next_cursor`; sizes describe the
  returned page, not the whole catalog. Reject obsolete query parameters explicitly
  rather than silently ignoring old cursors.

## 5. Phase 0 — Freeze contracts and executable acceptance cases

Dependencies: none. Implementation status: completed locally.

Files: existing API/schema/config modules; planned cursor helper; contract tests;
this plan and FE integration notes. No runtime feature is shipped in this phase.

- [x] Record the scope above, request/response DTOs, error taxonomy and nullability.
- [x] Define reusable scope projection, summary and viewer-context interfaces before
  adding routes; HTTP and assistant tools must use the same business services.
- [x] Fix the meanings of counts, structural metrics, provenance and recency below.
- [x] Freeze canonical batch hash encoding shared by runtime tests and frozen migration.
- [x] Establish route ordering for fixed paths such as `by-handle`/`search` versus IDs.
- [x] Create strict positive-ID, unique-list and cursor validation contract tests.
- [x] Document obsolete contracts to reject/remove; do not write compatibility parsers.
- [x] Define error handling with current safe `{error: code}` and request correlation.

Acceptance: every phase has a single target contract; no open choice requires a
second compatibility implementation. Product deferrals are represented by absent
features, not disabled tables/endpoints waiting to be used.

## 6. Phase 1 — Learning schema and data-preserving migration

Dependencies: Phase 0. Files:

- [Study models](../../apps/api/pycil/study/models.py)
- [Account schemas](../../apps/api/pycil/account/schemas.py)
- [Configuration](../../apps/api/pycil/config.py), [policy](../../config/config.yaml)
- [Migration revisions](../../apps/api/migrations/versions/)
- [Migration gate](../../apps/api/pycil/migrate.py), [schema verification](../../apps/api/pycil/database.py)
- New integration migration fixtures/tests.

Append proposed `0003_learning_batches_activity`; never edit `0001` or `0002`.

### Target persistence

**`UserSense` / `user_senses`** replaces `SenseMemory` / `sense_memory`, preserving:
user/sense PK, stability/difficulty, last review/due/rating, review/lapse counts,
created/updated timestamps and restrictive lexical FK.

Retain `(user_id, due_at, sense_id)` access. Remove the stability-ordering index if
its only consumer is the deleted weakest feature. Rename constraints/indexes safely.

**`ReviewReceipt` / existing `review_log` table** becomes an internal batch receipt:

```text
user_id + event_key UUID                  composite primary key
request_hash                             canonical SHA-256 digest
accepted_at                              UTC timestamp
activity_day                             frozen accepted local date
result JSONB                             complete original response
```

Keep receipts until account deletion. No raw-history endpoint, TTL, source node,
session identity, or per-question rows. Remove obsolete scalar/mastery columns.

**`user_daily_activity`**:

```text
user_id + day DATE                       composite primary key
applied_events                           nonnegative count
practice_events                          nonnegative count
```

### Upgrade transformation

- [x] Preserve every node/sense ID and existing FSRS state exactly.
- [x] Convert every old one-sense event to a one-item batch receipt, retaining its
  user/key, accepted time, rating, applied flag and original due-after snapshot.
- [x] Compute the same new digest for that one-item body; remove only mastery from
  the saved response. Do not replay FSRS during migration.
- [x] Backfill daily counts from all receipts, without filtering current membership.
- [x] Historical timezone-at-event was not stored: use each user's verified reporting
  timezone at migration time for old dates and explicitly document that limitation.
  New accepted dates are frozen and never recalculated later.
- [x] Migrate saved preferences using old effective Q/K, including K-only overrides:
  `max_sense_count = floor(effective_question_budget / effective_questions_per_sense)`.
  Freeze the inspected defaults Q=30 and K=3 in migration code; verify deployment
  baseline before production migration. Abort/report invalid legacy combinations.
- [x] Remove `question_budget` from saved settings and active config/schemas.
- [x] Rename limits to `max_questions_per_prepare`; default 100. Add batch/window
  bounds; remove mastery/history/weakest/forecast-only policy keys as their consumers go.
- [x] Keep historical revision transforms self-contained; never import changing
  runtime ORM/config/hash helpers into a migration.
- [x] Test upgrade from populated `0001` through all heads, and separately from
  populated `0002`, plus empty database and repeated migration gate.

Acceptance: existing identities, memberships and progress survive; old idempotency
keys remain meaningful for corresponding new one-item batches; activity backfill
matches the converted receipts. No new star/pin/schema artifacts are introduced.

This revision cannot truthfully downgrade multi-result receipts to the old scalar
contract. Refuse lossy downgrade; rollback after new writes requires a verified
pre-upgrade backup and corresponding old release, not an image-only swap.

## 7. Phase 2 — Atomic batch reviews and frozen activity

Dependencies: Phase 1. Files: study review service/API/schemas, models, FSRS wrapper,
account existence checks; new batch integration/concurrency tests.

### Request and response

```http
POST /v1/study/reviews
Idempotency-Key: <client-generated UUID>
```

```json
{
  "results": [
    {"sense_id": 123, "rating": "GOOD"},
    {"sense_id": 456, "rating": "AGAIN"}
  ]
}
```

Response: one batch `accepted_at` and `activity_day`, plus ordered item results with
`sense_id`, `rating`, `applied`, `accepted_at`, `due_after`. No mastery or session ID.

### Transaction algorithm

- [x] Validate strict unique positive sense IDs, native rating values, nonempty list,
  count bound and extra-forbid body. Reject the old single-item body.
- [x] Canonicalize `{results: [...]}` with fixed UTF-8 JSON/key/separator rules;
  preserve array order and hash with SHA-256. Reordered results are a changed batch.
- [x] Require account existence and acquire a transaction-scoped `(user,key)` lock.
- [x] Existing receipt + same digest returns its saved result without any new state,
  FSRS, time/day calculation or activity increment; different digest returns 409
  `review_batch_conflict`.
- [x] Validate all sense IDs in one indexed query before writing anything.
- [x] Acquire existing per-user/sense locks in ascending sense-ID order; read states
  in a batch. Response order remains original request order.
- [x] Capture one server UTC acceptance time and one current reporting timezone after
  lock acquisition. Read settings once for this acceptance; freeze resulting day.
- [x] Apply native FSRS exactly for missing state, `due_at <= accepted_at`, or AGAIN.
  Early HARD/GOOD/EASY produce activity with `applied=false` and no state mutation.
- [x] Write changed states, one immutable receipt and one daily aggregate increment
  in the same transaction. Any exception rolls all of them back.
- [x] Permit results for existing lexical senses after source revocation, without
  reopening the source or creating a lasting permission grant.
- [x] Account deletion cascades states/receipts/activity; no anonymous submission.

### Required tests

- [x] Empty/duplicate/boolean-ID/unknown-field/invalid-rating/101-item batches fail.
- [x] Missing sense after valid items causes no partial state/receipt/day write.
- [x] All ratings on NEW/DUE/equality-DUE/early states match native scheduling rules.
- [x] Early non-AGAIN preserves all state columns and never invokes FSRS.
- [x] Identical sequential/concurrent keys apply once; changed/reordered body conflicts.
- [x] Retry after later review returns original due-after and original accepted day.
- [x] Overlapping batches lock deterministically without deadlock.
- [x] Injected failure after computing/writing some states rolls back everything.
- [x] Acceptance across midnight/DST uses one server date; retries across timezone
  changes cannot produce another day or update old activity.

Acceptance: atomicity and idempotency are proven with real PostgreSQL concurrency,
not simulated by N single-sense requests. Keep feedback/grade separate from review.

## 8. Phase 3 — Maximum-sense preferences and explicit prepare selection

Dependencies: Phase 1; may develop alongside Phase 2 in the same unreleased branch.
Files: study preparation/API/schemas, account settings, config/policy, native content
tests. No new scheduling or question-generation engine.

```json
{
  "node_id": "00000000-0000-0000-0000-000000000001",
  "selection": "DUE",
  "max_sense_count": 10
}
```

- [x] `selection` defaults AUTO; omitted maximum uses effective saved preference.
- [x] NEW selects only missing user state in stable sense-ID order.
- [x] DUE selects only studied senses with due-at at/before one captured cutoff,
  oldest due first, then sense ID.
- [x] AUTO selects eligible DUE, then NEW, then NOT_YET_DUE if capacity remains.
- [x] Maximum means an upper bound; fewer or zero bundles is valid when genuinely
  insufficient ready content exists. No category fallback for NEW/DUE.
- [x] Validate requested/effective `max_sense_count * questions_per_sense <= 100`;
  reject impossible combinations rather than clipping silently.
- [x] Keep existing plan-entitlement lookup from current persisted account, not a
  stale detached actor. Preserve allowed question/format pairs and native grade policy.
- [x] Share authorized scope/readiness cutoff in repeatable-read selection; only
  examine later AUTO phases if capacity remains. DUE must not do unused NEW work.
- [x] Keep scope IDs in SQL and native count/allocation/retrieval batched for selected
  senses. Preserve unique questions and `learning_content_changed` conflict handling.
- [x] Return node/selection/maximum, actual sense/question counts, effective
  preferences and native bundles; counts must exactly match payload.
- [x] Preserve generated answer keys/explanations and current structured typed grades.
  No new normalized feedback DTO or paid grading call for multiple choice.
- [x] Pro-only typed grading remains; Free effective formats remain single choice.
- [x] Remove old budget acceptance and prepare mastery dependencies.

Tests: DUE-only/NEW-only isolation, default AUTO, exact cutoff, default/override limits,
sparse banks/no eligible questions, entitlement downgrade, no writes or paid provider
calls, correct native formats, bank-change conflicts and payload/count consistency.

Acceptance: Learn maps to NEW, Review to DUE, generic practice to AUTO without FE
post-filtering. Scheduler counts are not advertised as eligible-question counts;
action copy uses `new senses`/`due senses`, and FE handles a smaller prepared set.

## 9. Phase 4 — Summaries, activity, streak and review schedule

Dependencies: Phases 1-2; readiness/count semantics align with Phase 3.
Files: replace current study progress aggregation with focused services/API/schemas;
extend shared scope projection; add inline summary integration to library/discovery.

### 9.1 Summary meanings

Capture one `as_of` for the entire requested summary batch:

```text
NEW          no user_senses row
DUE          row exists and due_at <= as_of
NOT_YET_DUE  row exists and due_at > as_of
total = new + studied
studied = due + not_due
```

- [x] `GET /v1/study/progress?node_id=...` returns exact lightweight counts; omitted
  node resolves the actor's Library and returns the resolved node ID.
- [x] Count unique scope senses; do not join dictionary payloads, receipts, CEFR,
  weakest lists or activity merely to count progress.
- [x] Provide `last_studied_at = max(user_senses.last_review_at)` within the current
  scope, null when unstudied. It means latest applied review of a current scope sense
  anywhere, not session attribution or latest early practice.
- [x] Structural metrics distinguish immediate folders/decks/references from total
  reachable unique decks. Count references as placements, not copies of target decks.
- [x] Studied coverage is derived `studied / total`; zero denominator means no
  coverage value. It is not mastery or an aggregate of child percentages.
- [x] Author/public node learning counts always describe the authenticated viewer,
  not the author. Anonymous card summaries have lexical/structural counts with all
  personal fields null, not fictitious NEW counts or zero due counts.

### 9.2 Joint card summaries and no N+1

- [x] Expose `POST /v1/study/summaries` for bounded distinct `node_ids`, and optional
  `include=summary` on node/discovery metadata pages through the SAME service.
- [x] Authorize requested roots in batches. Resolve distinct frontiers jointly,
  preserving root-to-node/deck mappings and viewer-local shared work.
- [x] Extend the resolver beyond its current sense-only output so search, provenance
  and summaries reuse authorized node/deck projections without separate traversal.
- [x] Memoize identical resolved scopes/targets within the request; map aliases back
  to their displayed IDs, not duplicated memberships.
- [x] Deduplicate `(resolved_scope_group, sense_id)` and aggregate per scope in SQL;
  hydrate no full sense list into Python.
- [x] Guard existing physical budgets AND membership projection across distinct
  summary groups before fan-out aggregation. Reusing underlying decks does not make
  P different overlapping scope outputs free; cap that logical work at 200,000.
- [x] Whole request shares a deadline and one `as_of`. Do not reset the budget per card.
- [x] Invalid/unreadable explicit IDs fail the batch safely; no partial counts. A
  metadata-only retry can still render cards when requested enrichment is too large.
- [x] Flat 5-card and 50-card pages have batched authorization/count queries, not a
  loop invoking the current heavy progress function for each card.

FE folder pattern: one `GET /nodes?parent_id=...&include=summary` for child cards,
plus bounded independent folder summary/sense/activity reads as needed. Mixed Home
cards may use one POST summary batch. Never N progress requests for N cards.

### 9.3 Activity and streak

- [x] `GET /v1/study/activity?start_date=...&end_date=...`, both dates supplied together
  or both omitted; default trailing year, maximum 366 inclusive dates.
- [x] Return every requested date, including zero/future inactive dates, applied and
  practice counts and totals; no node/membership filter.
- [x] Return current reporting timezone, server `as_of` and frozen-day policy;
  historical dates retain their timezone-at-acceptance meaning.
- [x] Active day has at least one accepted sense result, including AGAIN and practice.
- [x] Current streak ends today, or yesterday if today is inactive, otherwise zero.
- [x] Longest streak uses all stored active dates, not only the returned date range.
- [x] Query indexed per-user daily rows, not raw receipt JSON/history scans on Home.
- [x] Prepare/grade/browse/retry do not add activity; organization changes do not remove it.

### 9.4 Review schedule

- [x] `GET /v1/study/review-schedule?node_id=...&start_date=...&end_date=...` uses current
  authorized scope, bounded future local dates, maximum 30; default upcoming 30 dates.
- [x] Count only `due_at > as_of`, including future times later today; equality is DUE.
- [x] Group in viewer's current timezone; return all dates with zeros, scope and `as_of`.
- [x] Explain that this is current scheduled work, not prediction; it changes after
  learning or Library edits. Overdue work belongs to Due, not future schedule.

Tests: partition identities, overlapping scopes, reference duplicates/cycles, guest
null learning, whole-request budgets, midnight/DST/leap day, yesterday/gap streak,
lifetime longest outside window, timezone change, deletion/unpublish invariance,
scope-only schedule and no partial timeout response.

Acceptance: Home/profile/folder/deck counts and event grids come from authoritative
data, with no session/minute/accuracy claims and no per-card fan-out.

## 10. Phase 5 — Sense browsing, search/sort and provenance

Dependencies: Phases 0-1 and shared scope projection in Phase 4.
Files: library senses/API/schemas, cursor/query helpers, native hydration, tests.

- [x] Preserve one pageable sense contract for all node types and anonymous ALL browsing.
- [x] Add optional literal case-insensitive lemma substring query `q` inside the
  selected authorized scope. Escape wildcard characters; max 200 characters.
  This is word-list search, not node FTS or whole-dictionary fuzzy search.
- [x] Add `SENSE_ID_ASC`, `LEMMA_ASC`, `LAST_REVIEWED_DESC`. Stable sense-ID tie-breaker;
  never-reviewed senses sort last for review order. Anonymous personal sort returns 401.
- [x] Apply text/state/order before LIMIT; sense state uses one page-traversal cutoff.
- [x] Include `last_reviewed_at` from native scheduling state; early non-applied practice
  leaves it unchanged. Keep due/rating/state and native lexical facts; no topic tags.
- [x] Add optional `include=examples,sources` with native stored examples and authorized
  source deck metadata. Enrichment is batched over returned IDs only.
- [x] Sources are unique canonical decks reachable in THIS scope, not every deck in the
  database. Several references to one deck do not repeat it or reveal private aliases.
- [x] Return up to 5 source decks per sense plus source count/more indicator; use one
  grouped query for the page. Overflow endpoint seeks sources within the same scope.
- [x] Source IDs/names and owner-derived editability never expose private parents or
  unreadable decks. Displayed reference breadcrumbs remain FE logical navigation.
- [x] Migrate cursors to the shared bound opaque scheme; no old `after_id` acceptance.
- [x] Full deck editor still returns complete membership IDs. Bulk removal from an
  owned deck uses final-state save, not selected browse-page IDs as the full set.
- [x] No new bulk removal operation from an aggregate folder; its ownership/multi-source
  implications are not defined by a checkbox in a screenshot.

Tests: match beyond first page, literal `%`/`_`, tie/null ordering, state equality,
cross-scope/query/order cursors, deleted anchors, multiple sources, source overflow,
revocation and page-batched examples/provenance with no per-sense queries.

Acceptance: Words tables can truthfully search/sort the selected scope and show source
information; flashcards can use lexical pages/examples without question-bank prepare.

## 11. Phase 6 — PostgreSQL Library search and Discovery

Dependencies: Phase 0 and shared authorized node projection. Append proposed
`0004_node_search`; no preferences table is part of this revision.

Files: library models/API/schemas; proposed `library/search.py` and catalog service;
migration and search/revocation/query-plan tests.

### Index and query design

- [x] Stored generated `search_vector` on node name and nullable description, name
  weight A and description B; explicit `simple` text-search configuration.
- [x] GIN index plus active published catalog/owner ordering indexes where justified.
- [x] Use `websearch_to_tsquery` with matching configuration and `ts_rank_cd` plus
  stable ID tie-breaker. Cursor rank representation must round-trip consistently.
- [x] Generated vector changes transactionally on rename/description save. Clients
  cannot supply vector/role/space. Do not concatenate all senses into node documents.

### Scoped search

- [x] `GET /v1/nodes/{id}/search?q=...&type=...&cursor=...&limit=...` accepts Library,
  folder or reference scopes; direct deck scope is rejected as not a node container.
- [x] Library scope includes readable own node names/reference labels and reachable
  referenced nodes; deduplicate canonical result IDs without copying remote documents.
- [x] Reuse resolved node IDs and intersect FTS candidates with the authorized scope.
- [x] No private target hydration through an unavailable reference; do not change
  visitor publication rules because an owner has private access.

### Discovery catalog

- [x] `GET /v1/discovery/nodes` browses with omitted `q` and searches with provided `q`;
  optional owner/type filters, bounded cursor and optional inline summary enrichment.
- [x] Return active published NORMAL nodes only; no private/system Library roots.
  Validate authoritative paths even when derived space says Published.
- [x] Catalog browsing orders creation timestamp/ID deterministically; query results
  use stable relevance order. Cursor is bound to all supplied filters.
- [x] Exclude unavailable public references for visitor browsing before final LIMIT.
- [x] Anonymous catalog has no personalized author/viewer learning data. Signed-in
  direct public learning remains allowed without adding a reference.
- [x] Do not expand the global catalog into a 10,000-node scope just to paginate it.
  Only explicitly requested result-card summaries use scope budgets.
- [x] No public star/learner rankings, exact global count, substring/fuzzy/autocomplete
  promise or hidden recommendation algorithm.

Tests: names/descriptions and weights, null description, mixed-language tokenization,
query/no-query/type/owner filters, relevance ties, broad/blank/oversize input, scope
binding, warm-cache unpublish/delete, corrupted derived space, anonymous/profile boundaries.

Acceptance: Library and Discovery are distinct real search APIs, not `/words/search`
renamed. GIN does not promise constant-time ranking; deadlines apply to broad queries.

PostgreSQL 18 references:
https://www.postgresql.org/docs/18/textsearch-tables.html and
https://www.postgresql.org/docs/18/textsearch-controls.html .

## 12. Phase 7 — Dictionary context and batch lexical hydration

Dependencies: Phases 1 and 4-5 reusable projections. Files: vocabulary API/schemas,
proposed viewer-context/hydration helpers using native lexical APIs, tests.

### Public batch previews

- [x] `POST /v1/words/previews` accepts unique positive `word_ids`, at most 30; returns
  native word identity/type and fully selected sense groups with definition, POS,
  tier, CEFR, register, IPA and up to 2 stored examples.
- [x] Bound total senses to 500 before hydration. Complete word grouping is essential
  for Select all: above the limit, fail and ask for a smaller batch, not partial words.
- [x] Use exported lexical contract queries/native sense batch APIs, not one `get_word`
  call per requested word. Do not fork private vendor internals or rebuild its wheel.
- [x] Validate/missing-content behavior is explicit; no provider calls during preview.
- [x] Native forms/relations remain on existing full word detail. Empty relations are
  legitimate; no fabricated ranked similarity or complete phrasal-family counts.

### Private viewer context

- [x] `GET /v1/me/words/{word_id}` loads real sense IDs and invokes the same bounded
  helper as `POST /v1/me/senses/context` with up to 100 selected sense IDs.
- [x] Return personal state/due/last-reviewed per sense, even if a previously learned
  sense currently belongs to no Library deck; do not create progress on lookup.
- [x] For membership context, resolve Library once and query readable containing
  canonical decks in that scope. Separate owner editability from mere readability.
- [x] Inline up to 5 containing decks per sense with count/more indicator; the private
  `/me/senses/{id}/decks` page exposes additional memberships without per-sense fan-out.
- [x] Word progress denominator is that actual word's senses, not total catalog hits.
  Native PHRASAL_VERB/IDIOM entry types are not manufactured POS values on `run`.
- [x] Document existing editable deck selection: load full `/editor`, union selected IDs in
  local draft, save once; search/filter changes never discard earlier selections.
- [x] Library budget errors fail requested context explicitly, never masquerade as
  `In 0 decks`. Independent public lexical detail remains available.

### Preserve native search boundaries

- [x] Keep `GET /words/search` and native Lexi engine unchanged as originally agreed.
- [x] Document real hit lemmas for suggestion chips and selected batch hydration.
- [x] Document FE filtering POS of fully loaded groups. It must label such filtering as the
  displayed result set, not a global POS-aware lexical search that does not exist.
- [x] Specify hiding/adjusting exact total-result and complete-family controls unless authoritative
  native data supplies them. No separate global lexical search rebuild in this release.

Tests: multi-sense word context, prior learning outside Library, repeated references,
multiple containing decks and overflow, read-only sources, hidden private decks,
revocation, batch bounds, native examples and draft membership preservation.

Acceptance: Dictionary progress and membership badges are viewer-specific real data;
modal sense groups hydrate in bounded batches, with no paid inference or per-sense scan.

## 13. Phase 8 — Handle and bio

Dependencies: Phase 0. Append proposed `0005_profile_handle_bio` after `0004` in the
single revision chain. Files: account models/schemas/API, invalidation, migration/tests.

```json
{
  "handle": "ninh",
  "bio": "Learning English every day."
}
```

- [x] Add nullable handle/bio to existing users; backfill null, not invented identities.
- [x] Handle: trim, canonical lowercase ASCII, 3-30 characters matching
  `[a-z][a-z0-9_]{2,29}`; unique at database level. Do not derive it from contact email.
- [x] Handle is optional until set; PATCH omission preserves it. Renaming is allowed;
  clearing an established handle is rejected. Existing stable user-ID URLs remain.
- [x] Bio: trim; maximum 500 characters; explicit null clears it. No HTML rendering.
- [x] Owner-only `PATCH /me/profile`; reject plan/settings/country/unknown writes.
- [x] Map concurrent unique-handle conflicts to 409 `handle_unavailable`, safely roll
  back, invalidate actor values where relevant and return the saved self profile.
- [x] Self/public profiles expose handle/bio and `joined_at` from existing created
  timestamp. Keep display name nullable; do not bundle a new display-name write or
  full Clerk synchronization subsystem into this task.
- [x] Add current-handle lookup with the same safe public response. After rename the
  old handle returns not found; no historical handle/redirect ownership service.
- [x] Read persisted profile data, not stale detached actor fields; no email/Clerk
  subject/private roots/settings/activity disclosed on public profile.
- [x] Profile learning sections are self-only; Published browsing remains public.

Tests: normalization, invalid/unicode/short/long handles, unique concurrent writes,
bio null/omission/length, unknown fields, handle rename/lookup, guest-safe output and
no extra provider dependency for reading/editing profile metadata.

Acceptance: existing users migrate without forced handles; real handle/bio can be
edited and shared safely, without country or expanded public learning exposure.

## 14. Phase 9 — Assistant and obsolete-contract cleanup

Dependencies: implemented contracts in Phases 2-8.
Files: assistant tools/graph and packaged `system_prompt.txt`; active source/config,
OpenAPI, tests and documentation. Preserve existing conversation persistence/protocol.

- [x] Update `learning_progress` tool to summary-only service, root IDs and bounded
  scope behavior; add read-only search/context tools only as thin shared-service calls.
- [x] Update list tools for cursor/limit and optional batch summaries; no one-card loop.
- [x] Preserve create/update/delete explicit approval guards and publication consent.
- [x] Keep complete editor IDs before full-state saves; assistant cannot replace a
  whole deck from a paginated browse response.
- [x] Do not add assistant review submission, profile edits, tags, preferences or
  import/translation tools merely because new HTTP read services exist.
- [x] Update packaged prompt/tool descriptions; preserve excluded local `prompt.md`.
- [x] Remove mastery function/config/storage/result fields, weakest queries/index,
  CEFR dashboard aggregation, raw history routes/models and old budget handling.
- [x] Retain lexical CEFR, native grade models and native FSRS scheduling behavior.
- [x] Migrate assistant conversation pagination to shared cursor conventions without
  changing AG-UI SSE/approval semantics. Old in-flight runs are quiesced at cutover;
  obsolete pending calls fail honestly, not through silent action translators.
- [x] Search active code/config/OpenAPI for obsolete contracts; distinguish frozen
  migrations/upgrade fixture strings from active compatibility code.

Acceptance: assistant reads describe the final backend truth, mutations retain
approval/ownership/publication gates and no deferred feature returns by another route.

## 15. Phase 10 — Correctness, performance and operational gate

Dependencies: all backend phases. Not a production operation or a claim of verified SLA.

### 15.1 Preserve the foundation regression matrix

- [x] Fresh/populated migration, corruption rollback and exact data preservation.
- [x] Concurrent root provisioning and system role protection.
- [x] Owner/visitor/anonymous boundaries; safe breadcrumbs and Published root.
- [x] Published-to-private reference restrictions and same-subtree publish validation.
- [x] Physical path create/move/delete matches a slow traversal oracle.
- [x] Depth/quota equality/+1, reductions of over-limit data, concurrent writes.
- [x] Indirect cycles, deep reference hops, repeated/overlapping targets and remote growth.
- [x] Live revocation across metadata, senses, search, context, summary and prepare.
- [x] Full 1,000-member editor rename/save; invalid save rolls back metadata/memberships.
- [x] Timeout recovery discards failed transactions and returns an explicit safe error.

### 15.2 Verify new contracts

- [x] Run phase-specific cases listed above as unit/integration/HTTP system tests.
- [x] Old single-review bodies/budget fields/history/cursors fail or are absent, no aliases.
- [x] No preference/tag/translation/country/import/audio endpoints or fields introduced.
- [x] Native question rendering formats/answer keys remain usable without normalization.
- [x] Error/CORS/body-size/request-correlation behavior covers new routes and failures.
- [x] Public learning projections never disclose author or unrelated user state.
- [x] Instrument SQL/native calls: card pages, batch preview and context do not exhibit
  per-result query loops. Record graph-frontier work separately from avoidable N+1.
- [x] Optional value-cache failure does not change SQL truth. Redis remains required
  for runtime coordination/readiness; do not claim complete Redis outage is harmless.
- [x] No permission grants, expanded scopes, prepare results or personal summaries are
  persisted in cache by default; warm caches cannot bypass a later access check.

### 15.3 EXPLAIN matrix

Save `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and query-count evidence for:

- Child metadata and inline/batch card summaries: 5 versus 50 cards.
- Empty/small/1,000-sense decks and folder scopes near membership budgets.
- Sparse/no-match NEW/DUE/search, lemma/review sort and provenance/context overflow.
- Duplicate-heavy overlapping folders and repeated aliases to one public target.
- Reference cycles/many frontiers and warm/cold scope reads.
- AUTO filled by DUE: later NEW/early phases not executed.
- Scarce question readiness and batched native retrieval.
- Scoped FTS, broad global FTS, owner/type catalog browsing and public authorization.
- Batch receipt replay, overlapping writes and shared daily-row contention.
- Native lexical search cold/refresh: its existing global projection rebuild is
  measured separately, never described as constant-time or page-local.

Inspect actual rows, loops, filtered rows, buffers, heap fetches and spills. A small
scoped relation seq scan can be appropriate; a selective request unnecessarily
scanning global user progress or all dictionary payloads is not.

### 15.4 Capacity/load evidence

- [x] Small deterministic CI fixtures plus an opt-in isolated performance suite.
- [x] Representative multi-tenant medium fixture: 1,000 users / 10,000 nodes /
  100,000 states and receipts, plus maximum-membership hot/remote scopes.
- [ ] Resource-gated large tier of 100,000 users / 1,000,000 nodes /
  10,000,000 progress rows plus receipts, subject
  to available disk/memory/time. Do not run the large tier without resource approval.
- [x] Maximum membership owners/scopes, hot public targets and overlapping writes are
  separate workloads from typical users, not hidden by averages.
- [ ] Record hardware, PostgreSQL settings, indexes/statistics, API process count,
  cache state, concurrency, workload mix, p50/p95/p99, throughput, errors and lock waits.
- [ ] Establish target-environment latency/throughput thresholds before capacity
  signoff; none are invented in this plan. Missing target/resources remains a gate,
  not a claim that passing unit tests demonstrates scale.
- [x] Optimize within approved query/index/batching architecture when evidence fails;
  no silent new stats cache/worker or smaller fixture chosen to conceal the failure.

### 15.5 Executable verification

From repository root, after implementation:

```sh
make lint
make test-unit
make test-api
```

Targeted automatic disposable-store runs resolve paths relative to `apps/api`:

```sh
python scripts/test_api.py tests/integration/test_library.py -q
python scripts/test_api.py tests/integration/test_learning_pipeline.py -q
```

Add new migration/batch/activity/search/context/profile/performance test files and
document their exact selections when they exist. Do not cite nonexistent tests as passed.
Direct CI pytest continues using its isolated service URLs. Do not use application
`DB_URL`/`REDIS_URL` as a fallback or restore removed environment prefixes.

From `apps/api`, wheel verification:

```sh
uv build --wheel --out-dir /tmp/opencode/pycil-completion-build
```

- [x] On disposable databases, rehearse explicit Lexi -> Pycil -> checkpoint migration
  order, repeated upgrade and Alembic drift check; do not edit externally owned DDL.
- [x] Verify startup schema checks match new head and never migrate/repair automatically.
- [x] Export OpenAPI without provider startup; validate request contracts and absent old APIs.
- [x] Validate runtime/test Compose, deployment shell and packaged prompt; use dummy
  addresses for configuration checks, never print secrets or deploy as a test.
- [x] Run `git diff --check` and prove unrelated changes were not reverted/restored.

Acceptance: correctness evidence is complete; query/load evidence is archived with
limits and observed failures. Performance signoff remains separate when target
thresholds/resources are unavailable.

## 16. Phase 11 — Documentation and FE integration handoff

Dependencies: stable implemented backend contract; FE code needs a supplied target.

- [x] Update account/library/vocabulary/study/assistant docs, configuration/data model,
  migration/testing/deployment notes and implementation status as features land.
- [x] Record the reduced release scope and deferred star/pin/tags/translation/country
  features in backend documentation without claiming those features are implemented.
- [x] Write a dedicated English FE contract with real complete examples, enums,
  nullability, cursor rules and error actions; regenerated OpenAPI is authoritative.
- [x] Include a feature matrix mapping retained controls in each supplied screen to
  implemented operations. Hidden/deferred controls must not get fake FE data.
- [x] Document bearer-token auth/CORS, matching Clerk instance, provider configuration,
  real vocabulary/question readiness and worker availability for the integration host.
- [x] Expose safe supported learning pairs/limits/entitlements in self profile metadata
  from product policy. No provider configuration/secrets or separate feature-flag system.
- [x] Supply executable scenario setup using disposable data: empty user, multi-sense
  word, new/due/early states, duplicate memberships, published target/reference,
  revoked reference, no-ready-bank, large scope and unknown batch acceptance.
- [x] Specify that FE session/draft storage remains local. Persist frozen result body/key before
  first submission and retry identically; distinguish uncertain from confirmed success.
- [ ] Define recall-rating UI/aggregation before FE completion integration. Generated
  Correct/Incorrect alone does not imply GOOD/EASY. No automatic backend mapping added.
- [x] Specify lexical pages/examples for flashcards; flip/index/shuffle add no activity.
- [x] Specify NEW/DUE labels, studied coverage, accepted events and future review counts;
  remove mastery, minutes, session counts, learners/categories and recommendations.
- [x] Specify same-device local draft/history for Continue/recent lookups if desired;
  do not promise cross-device resume or add lookup telemetry in this backend plan.
- [x] Explain ownership, references, safe publication, smaller prepared batches,
  loading/empty/unavailable/error and Pro-only typed grading states.

FE implementation requires an approved product target and unprovided integration-host
credentials/artifacts. Local `apps/web` starter/showcase files are not silently chosen
or overwritten as that target. Backend implementation/tests/handoff proceed independently.
The checked handoff items specify FE behavior, not claims that UI screens were implemented.

Acceptance: FE has a stable real-data contract for the retained scope, not a promise
that every historical screenshot metric has been implemented.

## 17. Delivery dependencies and stopping points

| Phase | Requires | Exit evidence |
| --- | --- | --- |
| 0 Contract | Current source and latest decisions | Strict DTO/error/cursor/hash tests and scope freeze |
| 1 Learning migration | 0 | Empty/populated upgrade, preserved state/keys/settings/activity |
| 2 Batch writes | 1 | Real transactional/concurrent replay and rollback tests |
| 3 Prepare | 1 | Selection/readiness/entitlement/no-write tests |
| 4 Stats/activity/cards | 1-2, prepare semantics | Exact summaries/date/streak/schedule and no-N+1 budgets |
| 5 Sense browse | 0-1, scope projection | Whole-scope query/sort/cursor/provenance tests |
| 6 Search/Discovery | 0, scope projection, 0004 | Index/search/authorization/pagination tests |
| 7 Dictionary context | 1, scope projection, 5 | Native batch hydration/private membership tests |
| 8 Profile | 0, ordered 0005 migration | Handle/bio uniqueness/lookup/privacy tests |
| 9 Assistant/cleanup | 2-8 | Approval regressions and absent obsolete contracts |
| 10 Verification | Backend phases | Suite/migrations/OpenAPI/build/query evidence; separate capacity gate |
| 11 Handoff | Stable contract | English docs/examples/scenarios; supplied FE target for actual UI |

Recommended sequential execution is 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9
-> 10 -> 11. Phase independence does not authorize agents, parallel branches or
production rollout. Each implementation checkpoint records completed tasks, tests,
failures and next dependencies; no phase is marked complete merely because its schema exists.

Useful backend handoff milestones:

1. After 1-4: final Learn/Review/completion and truthful Home event statistics.
2. After 5-8: retained Words/Dictionary/Discovery/Profile data and queries complete.
3. After 9-11: cleanup, operational evidence and final FE contract ready.

## 18. Cutover, rollback and safety

- This is a deliberate breaking release, not old/new clients behind a dual parser.
- Append revisions in order: existing 0002 -> 0003 learning -> 0004 node search ->
  0005 profile. Proposed filenames may change; the transformation order/invariants may not.
- Quiesce old API/worker writes and assistant in-flight runs before the explicit
  migration gate; back up the exact approved target and rehearse restore first.
- External schema ownership remains Lexi and checkpoints; Pycil owns only its DDL.
- Deploy matching new backend/client contracts and fresh cache namespace; do not
  flush shared Redis or retain old cached-payload parsers.
- Refuse a lossy downgrade. Restore the verified pre-upgrade backup plus compatible
  old release when necessary; document loss of post-backup writes, do not conceal it.
- Do not commit/push/deploy or mutate production as part of plan authoring/testing.
- Preserve dirty `.gitignore`, deleted legacy docs, local files and unrelated work.

## 19. Risk register and decisions outside this plan

| Risk / dependency | Control / honest status |
| --- | --- |
| Old events lack timezone-at-acceptance | Document migration-time timezone backfill; freeze new days |
| Old Q/K defaults differ on deployment | Verify baseline before upgrade; frozen transform, no guessing |
| Batch receipt growth | Account-local indexed keys, retained guarantee; no TTL to fake capacity |
| Joint summaries amplify overlapping scopes | Request-local grouping plus physical/logical work budgets |
| Broad FTS ranking/global lexical refresh | Measure, index and time-bound; no constant-time claims |
| Concurrent edits/ordinary pagination mutation | Preserve atomic save; refresh lists after writes; no snapshot promise |
| Profile handle rename/conflict | Database uniqueness; 409; stable UUID identity; no redirect-history system |
| Public data revoked after delivery | Subsequent reads deny; cannot erase previously delivered client content |
| Screenshot-only goals/time/courses/metrics | Out of scope; FE adapts copy/controls, no made-up server statistics |
| Missing FE source/target | Backend and handoff proceed; no silent scaffold |
| Missing live dictionary/provider/Clerk integration setup | Explicit host-readiness checklist; do not call test replacements production-ready |
| Missing benchmark target/resources/thresholds | Record capacity gate as pending rather than claiming release scale |

No interview is required to begin the backend phases with the conservative defaults
in this plan. Actual FE target, production approval and capacity thresholds/resources
are external delivery gates, not permission to expand feature scope.

## 20. Final definition of done

- [x] Foundation invariants preserved; backend work complete and external gates identified.
- [x] Learning rename/settings/receipt/activity migrations preserve representable data.
- [x] NEW/DUE/AUTO and batch-only retries match the exact contract.
- [x] Lightweight summaries, joint card counts, immutable activity/streak and schedule work.
- [x] Sense query/sort/provenance and viewer dictionary context are authorized and bounded.
- [x] Library FTS and Discovery work with final cursors and no private leakage.
- [x] Handle/bio work; country/tags/preferences/translation/import/TTS remain absent.
- [x] Native generated feedback and existing typed grading preserved without extra subsystem.
- [x] Mastery/weakest/raw-history/old budget/runtime aliases removed; lexical CEFR retained.
- [x] Assistant tools use current services and mutation approval remains enforced.
- [x] Backend supports joint/page batches, not mandatory FE/SQL fan-out; bounds fail honestly.
- [x] Fresh/populated migrations, suite, OpenAPI, build and operational checks have evidence.
- [x] Query plans/representative smoke load archived; production capacity gate explicit.
- [x] English docs and FE scenario/error handoff reflect implemented, not planned, APIs.
- [x] No unrelated changes reverted; no frontend scaffold, production action or commit implied.
