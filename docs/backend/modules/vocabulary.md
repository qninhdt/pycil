# Vocabulary, search and generation

## Ownership

`vocabulary` owns shared lexical content, generation, reference evidence, relations,
translation and Tantivy search. Study owns question banks and grading. HTTP adapters
and assistant tools call these application functions directly. There is no external
library facade, duplicate ORM base or separately deployed vocabulary service.

The required immutable reference is imported from `data/reference.jsonl` into two
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
A disk index is rebuilt when its publication fingerprint differs from the database.
Word and consumed-reference markers commit with their search documents; startup derives
the published word count/maximum ID and consumed-reference count from these markers,
alongside the immutable reference count/maximum ID recorded during rebuild. An unrelated
word update cannot mark unpublished database content as indexed. Complete disk indexes
are reused after restart, and every process using the same directory follows its commits.
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

Publication commits PostgreSQL first, replaces that word's index documents, removes
consumed references, commits/reloads Tantivy, then returns success. Each update projects
one word in five SQL queries without whole-dictionary fingerprint aggregates. Native writes are
serialized by Tantivy's cross-process writer lock and joined on cancellation. Existing
readers can finish with the old snapshot.
A failed index update fails the job and keeps valid committed content for a subsequent
explicit retry or startup rebuild when publication markers differ. Rebuild indexes
references before words so the words remove their consumed reference documents in the
same commit. Schema version changes create a new versioned directory and require a
first-start rebuild; older directories are not deleted automatically. Edits that bypass
publication without changing counts or maximum IDs need the index directory removed
before restart.

Batch previews hydrate selected IDs in bounded SQL batches rather than calling word
detail per result. Complete groups must fit configured sense limits; oversized requests
fail. Shared content caching excludes private progress. Viewer projections authorize
readable containing decks live and keep prior personal state after membership revocation.

## Generation

Submit a reference handle plus target text. The pipeline validates source/evidence,
builds an inventory, then enriches batches of at most eight senses concurrently. Invalid
citations, forms, patterns or target-marked examples never publish. Sibling work is cancelled
and joined after failure. Completed canonical words are reused; overlapping publication
uses database advisory locks and a single transaction.

Reference-key and normalized word-input singleflight live in the API process. Jobs use
bounded concurrency per process and a configured deadline after acquiring a slot.
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
