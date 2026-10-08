# Study: preparation, grading, batch reviews and reporting

The current working-tree contract is breaking. There is no scalar review parser,
question budget, mastery/weakest dashboard, raw history route or learning-session service.
Question answer keys/explanations and typed grading remain native Lexi artifacts.

## API

| Operation | Result |
| --- | --- |
| `POST /v1/study:prepare` | Read-only native question bundles |
| `POST /v1/study:grade` | Pro-only native typed grade; no progress/activity write |
| `POST /v1/study:submitReviews` | Atomic batch and immutable original-result replay |
| `GET /v1/study/progress` | Exact lightweight scope summary |
| `POST /v1/study:batchSummarize` | Joint bounded card summaries; optional public viewer |
| `GET /v1/study/activity` | Frozen accepted dates, zero-filled grid and streaks |
| `GET /v1/study/review-schedule` | Current future due counts, not predictions |

All except public summaries require sign-in. Readable public nodes are directly
learnable without saving them. Home counts only currently Library-reachable senses.

## Preparation

```json
{"node_id":"00000000-0000-0000-0000-000000000001","selection":"DUE","max_sense_count":10}
```

Use a real readable UUID. Selection defaults AUTO; omitted maximum uses saved settings.
Default maximum is 10 senses with 3 questions each; K is 1-7 and maximum*K must not
exceed 100. Invalid combinations fail rather than clip.

NEW selects missing user state by ID. DUE selects due-at <= one cutoff, oldest due
then ID. AUTO executes DUE, NEW, early phases in sequence, stopping when full;
NEW/DUE never fill from another category. A repeatable-read selection joins scoped
membership and neutral question readiness. Only selected senses are native-batch
hydrated. Retrieval after selection can return 409 `learning_content_changed`.
There are no writes, reservations, question generation or paid preparation calls.

Response: `node_id`, `selection`, `max_sense_count`, actual sense/question counts,
effective preferences, native sense bundles and reasons. Sparse/unready content can
return fewer or zero senses. Due counts are not eligible-question-bank counts.

Native type/format pairs and configured rating-based caps control shuffled options,
multiple choice, single-word and short-answer allocation. Free excludes typed formats;
an infeasible effective selection returns `infeasible_learning_preferences`. Current
persisted plan and settings are authoritative, not a detached actor's stale values.

## Grade

```json
{"question_id":123,"format":"SINGLE_WORD","answer":"bank"}
```

Requires current ADVANCED_GRADING entitlement. SINGLE_CHOICE, blank or >8,000-character
answers fail. Native errors map to 404 `question_not_found`, 422
`unsupported_question_format`, and 503 `grading_unavailable`. Typed grading can call
configured paid providers in real deployments; tests block/substitute that boundary.
There is no normalized feedback subsystem or automatic recall-rating conversion.

## Atomic reviews

```http
POST /v1/study:submitReviews
Idempotency-Key: <client-generated UUID>
```

```json
{"results":[{"sense_id":123,"rating":"GOOD"},{"sense_id":456,"rating":"AGAIN"}]}
```

1-100 distinct strict positive sense IDs; ratings AGAIN/HARD/GOOD/EASY. Persist the
body and UUID locally before sending. Canonical UTF-8 SHA-256 uses sorted JSON object
keys, compact separators and preserved result-array order. Changed/reordered results
with an old key return 409 `review_batch_conflict`.

One transaction locks the user/key, validates lexical IDs together, takes sense locks
in sorted order, reads states together, then records one server acceptance time/local
day. Missing accounts/senses or any write failure rolls everything back. Identical
retries return saved JSON before scheduler/activity work, even after later reviews or
timezone changes. Receipts have no TTL and remain until account deletion.

FSRS applies iff state absent, due-at <= acceptance time, or AGAIN. Early positive
practice changes no state column and never invokes FSRS. Results contain sense/rating,
applied flag, accepted time and original due-after. The batch adds its accepted time,
frozen activity day and ordered item results. No mastery/session/source attribution.
Known lexical results remain submittable after source revocation; no node access is granted.

`UserSense` preserves native stability/difficulty, last review/due/rating and counters.
The installed binding uses native default parameters, elapsed whole UTC days,
retention 0.9 and interval cap 365 days. No alternative scheduler is implemented.

## Summaries

Progress resolves an optional node, default Library. Unique total = new + studied;
studied = due + not_due. `last_studied_at` is the maximum applied review of a current
scope sense anywhere, not session/practice attribution. Coverage is studied/total,
null for an empty scope. Structural counts distinguish immediate folders/decks/
references and reachable unique decks. Guests get null personal fields.

Explicit summary batches accept up to 50 distinct `node_ids`. Child/discovery pages
support `include=summary` using the same service. Roots/graph frontiers are authorized
jointly, identical deck sets memoized, `(scope_group,sense_id)` deduplicated in SQL.
One request deadline and cutoff apply; physical work and distinct-scope logical
membership projection are separately bounded. There is no per-card heavy report
loop or persistent summary cache. Oversized enrichment fails completely; FE may
retry a metadata-only page. Never sum overlapping children to get a parent total.

## Activity and schedule

Activity accepts paired `start_date`/`end_date`, at most 366 inclusive dates; omitted
dates select the trailing 366 dates. Applied/practice event counts include AGAIN,
not prepare/grade/browse/replay. Dates are frozen at acceptance in the then-current
timezone; timezone changes and Library edits never regroup/remove them. All dates,
including inactive ones, are returned. Current streak ends today or yesterday if
today inactive; longest uses all active stored days, not the displayed window.

Review schedule has optional node and paired dates, at most 30 inclusive future
dates, default upcoming 30. It counts only due-at > cutoff, including later today,
grouped in the current timezone. Equality/overdue belongs to Due. This read changes
with progress/organization, not historical activity. Both return timezone/as_of.

Historical events migrated without recorded timezone-at-acceptance use each user's
timezone at upgrade. That limitation cannot be retroactively repaired from absent data.

## Evidence

- [Native preparation/grade/rating matrix](../../../apps/api/tests/integration/test_learning_pipeline.py)
- [Reporting](../../../apps/api/tests/integration/test_progress.py)
- [Atomic/concurrent batches and FE contracts](../../../apps/api/tests/integration/test_completion.py)
- [Populated learning migration](../../../apps/api/tests/integration/test_learning_migration.py)
- [Schemas](../../../apps/api/pycil/study/schemas.py), [services](../../../apps/api/pycil/study/progress.py)
