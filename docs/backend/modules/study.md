# Study: local learning, artifact preparation and evidence tracking

Lexi persists `QuestionArtifact`; Pycil builds public runtime `Question` samples. The eight public types and formats stay separate from six storage/generation artifact types. The backend stores personal Memory/Mastery and immutable result receipts. The session lives on the client.

## API

| Operation | Result |
| --- | --- |
| `POST /v1/study:prepare` | Plan public pairs, retrieve/refill artifacts, build runtime samples |
| `POST /v1/study:grade` | Pro typed diagnostics from saved artifact and answer |
| `POST /v1/study:submitResults` | Atomic diagnostic tracking and grouped state updates |
| `GET /v1/study/progress` | Exact scope summary |
| `POST /v1/study:batchSummarize` | Bounded card summaries, optional public viewer |
| `GET /v1/study/activity` | Frozen acceptance dates and streaks |
| `GET /v1/study/review-schedule` | Current future due counts |

## Preparation

```json
{"node_id":"00000000-0000-0000-0000-000000000001","selection":"AUTO","max_sense_count":10,"questions_per_sense":2}
```

N is 1–20; K is 1–3, default 2. NEW selects absent personal states. DUE selects due states, oldest due then ID. AUTO fills due, new, then future states. Selection uses a repeatable-read SQL scope; bank readiness does not exclude a Sense.

One pair/level matrix serves Free and Pro. Free effectively uses SINGLE_CHOICE while preserving saved typed preferences. Pro uses its selected supported pairs. Available levels at or below the user's level receive weights `2**(level-user_level)`; sample a level, then a uniform pair within it. If no selected pair fits, use the minimum available level. K draws allow repetition.

Aggregate `(sense_id, question_type, quantity)` and call native retrieval with `generate=True`, batch size 8. Lexi fills contextual shortages, saves the full batch and returns the requested capacity. WORD_DEFINITION and WORD_TO_USAGE each use one row per Sense/namespace. Shared views use the maximum demand, not the sum. Pycil builds each occurrence independently from returned artifacts. No runtime question or session is persisted.

## Grading and local session

```json
{"question_artifact_id":123,"question_type":"DEFINITION_TO_WORD","format":"SINGLE_WORD","answer":"bank"}
```

Quiz diagnostics are computed locally. Typed answers, including null for “don't know,” go to backend grading. Lexi reads the artifact and current lexical meaning from its database. The response contains artifact/type/format references and task-specific diagnostics; grading writes no learning state.

The client uses local occurrence indices, rounds of eight and retry-first scheduling. Initial answers may have at most two practice retries. Lock and persist the answer/timestamp before grading; a network error keeps them locked and consumes no attempt. Retrying practice never replaces the initial diagnostic. Explicit early finish submits completed initial diagnostics only; exit alone submits nothing. Preparation timeout is 30 seconds.

## Tracking, Memory and Mastery

```http
POST /v1/study:submitResults
Idempotency-Key: <client-generated UUID>
```

```json
{"results":[{"question_artifact_id":123,"question_type":"DEFINITION_TO_WORD","format":"SINGLE_CHOICE","diagnostics":{"correct":true},"answered_at":"2026-10-11T10:00:00Z"}]}
```

Accept 1–60 initial results, including repeated artifacts. Persist the ordered body/key locally before sending. The backend consumes diagnostics without regrading or storing answers/session snapshots. Unknown references, incompatible types/formats and future timestamps fail atomically. Reusing a key with changed data returns `review_batch_conflict`; identical replay returns the original receipt.

Correct single-word/definition diagnostics credit the matched Sense; failure affects the requested Sense. Definition matches must belong to the target Word. Convert diagnostics using the [accepted rubrics](../../../question-generation-design.md), then group by evaluated Sense. Bulk reads/upserts and a user transaction lock avoid per-question SQL. Receipts retain converted evidence, opponent Elo and policy version.

Each `(user, sense)` has shared Elo and Memory. For one group, any recall 0 invokes FSRS Again; otherwise observed recall 1 invokes Good. All-null recall preserves S/D. A new all-null state starts S=1 day, D=5. Every applied group advances exposure and due; FSRS uses native defaults, same-day behavior, retention .9 and a 365-day maximum. Older evidence remains logged and cannot overwrite newer state.

Mastery uses fixed opponents by public pair level and classic Elo scale 400/K=32. Compute all expectations from the old Elo; delta is `32 * weight * mean(performance-expected)`, omitting null performance. Weight is elapsed exposure time / 24 hours, clamped to [0,1], or 1 for a new Sense. One group gets one budget. Elo maps to five display/planning levels.

The response contains grouped updated states and immutable question evidence. The receipt and daily activity commit in the same transaction. No backend session table exists.

## Summaries

Progress resolves an optional node, default Library. Unique total = new + studied;
studied = due + not_due. `last_studied_at` is the maximum exposure of a current
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
dates select the trailing 366 dates. Applied/practice counts record evaluated Sense groups,
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

- [Native preparation, grading and evidence tracking](../../../apps/api/tests/integration/test_learning_pipeline.py)
- [Reporting](../../../apps/api/tests/integration/test_progress.py)
- [Atomic/concurrent batches and FE contracts](../../../apps/api/tests/integration/test_completion.py)
- [Current schema checks](../../../apps/api/tests/integration/test_fresh_schema.py)
- [Schemas](../../../apps/api/pycil/study/schemas.py), [services](../../../apps/api/pycil/study/progress.py)
