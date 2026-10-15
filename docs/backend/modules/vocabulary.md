# Vocabulary, search and generation

## Ownership

`vocabulary` owns shared lexical content, generation, reference evidence, relations,
translation and Tantivy search. Study owns question banks and grading. HTTP adapters
and assistant tools call these application functions directly. There is no external
library facade, duplicate ORM base or separately deployed vocabulary service.

The required immutable reference is imported from `data/reference.jsonl.gz` into two
PostgreSQL tables. API runtime reads those rows; it does not open distribution artifacts.
WordNet is optional local evidence. Generated content is optional and imported manually
as PostgreSQL data; setup does not ship or automatically load a generated-content seed.

## API

| Operation | Authentication / result |
| --- | --- |
| `GET /v1/words:search` | Optional; ranked word/reference hits |
| `GET /v1/words/{word_id}` | Optional; complete word and senses |
| `POST /v1/words:batchPreview` | Optional; bounded complete word groups |
| `GET /v1/me/words/{word_id}` | Required; viewer progress/membership |
| `POST /v1/me/senses:batchReadContext` | Required; bounded viewer projection |
| `GET /v1/me/senses/{sense_id}/decks` | Required; authorized deck overflow |
| `POST /v1/words:generate` | Required; Redis-backed task acceptance |
| `GET /v1/word-tasks/{task_id}` | Required; current shared task status |

Use [OpenAPI](../openapi.json) for exact contracts. Controlled values are lowercase.
Reference handles are opaque identities returned by search, not saved sense IDs.

## Search and projections

The index is opened before serving: in memory, or on disk under `SEARCH_INDEX_PATH`.
One lifetime writer per directory polls PostgreSQL content revisions. Other workers use
its committed reader and retry ownership with jitter; independent directories each poll
all changes. A compatible cursor is reused after restart/takeover. A new schema directory
bootstraps from one repeatable-read snapshot and catches up after its recorded high-water
revision. Request handlers do not acquire writers.
Searches use the current reader without SQL. Ranking follows `exact`, `prefix`, `substring`, then
`fuzzy`; generated words precede reference hits within a match class. Aliases/forms and
licensed patterns retain exact-match behavior. Consumed references disappear after the
corresponding word is published. Word-string generation accepts an exact match, not a
suggestion-only fuzzy/prefix hit.

Fallback queries are constructed only when needed. Substring queries of at least three
normalized characters intersect trigram postings and verify the full substring in each
candidate; shorter queries retain regex matching. Pattern candidates are read in sorted,
growing pages until enough generated exact matches are available or candidates are
exhausted. Neither path imposes a candidate cap that can discard valid hits.

Content and deterministic JSON Patch history commit in the same PostgreSQL transaction.
Revisions cover words and their owned children, artifact payloads/ordering, and themes.
The shared publication lock is acquired last; sequence IDs use `CACHE 1` and are committed
in scan order. Deletes retain tombstones and cascade-affected patches. The owner coalesces
bounded revision batches, reads current search projections in one SQL snapshot, and commits
documents plus cursor atomically. Unlinking/deleting a generated word restores an immutable
reference when no completed word consumes it. Theme/artifact-only batches advance the cursor
without creating search documents.

Generation waits for the committed revision to be visible locally before reporting ready.
Waiting holds no database connection. Publication timeout/failure preserves committed content;
retry does not buy another generation when canonical content already exists. Transient database
errors retry with the same writer, while fatal native failures mark readiness unhealthy and
release ownership. Cancelled native work is joined before shutdown releases its dependencies.

Supported direct edits/deletions must use the transactional content/history functions;
raw SQL bypassing them is outside the mutation contract. Existing content needs an explicit
paused-write baseline. Retain the complete baseline/patch chain. Reference replacement, schema
changes and older-database restore require reviewed derived-index invalidation; an ahead-of-DB
cursor is rejected. See [the operational procedure](../operations/migrations.md).

Neutral content uses separate process-local Word metadata and Sense caches. Word metadata
contains ordered Sense IDs; complete responses reuse those Sense objects without caching
an assembled Word. Retained lexical DTOs are frozen slotted Pydantic dataclasses with tuple
collections; HTTP arrays and field aliases stay unchanged. Themed reads bypass neutral caches.
A complete Word/Sense hit needs no SQL. Partial Sense misses use the existing deduplicated,
ordered, bounded batch loader; missing Senses trigger one authoritative Word reload.

Batch previews, library examples, study preparation and Assistant lexical hydration reuse
the Sense cache after authoritative selection. Complete groups must fit configured sense
limits; oversized requests fail. Shared content caching excludes private progress. Viewer
projections authorize readable containing decks live and keep prior personal state after
membership revocation. Committed lexical edits clear both neutral caches in the writing
process; TTL bounds stale data in other processes. Artifact caching remains independent.

## Generation

Submit a reference handle plus target text. The pipeline validates source/evidence,
builds an inventory, then enriches batches of at most eight senses concurrently. Invalid
citations, forms, patterns or target-marked examples never publish. Sibling work is cancelled
and joined after failure. Completed canonical words are reused; overlapping publication
uses database advisory locks and a single transaction.

Reference-key and normalized word-input singleflight live in the API process. Each process
runs at most eight generation pipelines and admits at most 24 unfinished jobs (eight active
slots plus 16 pending slots). Jobs retain admission capacity until final status publication
finishes. A new distinct job when full returns `503 generation_overloaded` without creating
a task or Redis status; duplicate requests still return the existing job. The configured
generation deadline starts after acquiring an active slot.
Task status is stored in the existing Redis namespace before acceptance, so any API
process can poll it. Each initial/final status write has a 24-hour TTL. They finish with
`succeeded` / `ready` only after search publication; timeout/cancellation/failure are
sanitized. Redis read/acceptance failures return `503`, while missing/expired task IDs
return `404`. Final status write failures are logged and may leave the initial `running`
status until expiry. Graceful shutdown publishes interruption; a worker crash loses its
unfinished jobs and may also leave `running` until expiry. Jobs are not recovered or
deduplicated across processes; committed words remain reusable on retry. Word generation
does not create personal learning state or question banks.

Local prompts belong to the owning module. Structured provider parsing/retries and usage
measurement belong to infrastructure. Whole-operation logging carries correlation,
outcome and duration. Langfuse and OpenTelemetry exporters remain deferred.

Relation resolution uses [Pydantic decision models](../../../apps/api/pycil/vocabulary/relations/decisions.py)
with the relation rule, neutral evidence and current candidate senses. Instructor owns
request rendering and answer validation. The domain persists a selected current candidate
or the explicit `no_candidate` outcome; independent edge failures remain isolated.

## Evidence

- [Pipeline](../../../apps/api/pycil/vocabulary/generation/pipeline.py), [jobs](../../../apps/api/pycil/vocabulary/generation/jobs.py)
- [Search](../../../apps/api/pycil/vocabulary/search.py), [batched content](../../../apps/api/pycil/vocabulary/words.py)
- [Generation/publication/retry](../../../apps/api/tests/integration/vocabulary/test_generation.py)
- [Shared status, singleflight and cancellation](../../../apps/api/tests/integration/vocabulary/test_jobs.py)
- [Reference import](../../../apps/api/tests/integration/vocabulary/test_reference_import.py)
