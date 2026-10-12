# Vocabulary, lexical search, and generation

## Responsibility

Lexi owns the shared lexical model and native APIs for words, senses, previews, question
banks, search, generation, and grading. Pycil exposes a narrow HTTP surface and owns
process-local singleflight generation tasks. There is no copied Pycil dictionary model,
per-user word copy, or bespoke question-store service.

The dependency is the reviewed local wheel under `vendor/lexi-ai`, verified with
checksums and provenance. The required project-owned reference.sqlite is downloaded
and imported into
PostgreSQL `lexi_reference` by the migration gate. API do not require a
reference file. WordNet is optional generation evidence; missing corpus data is skipped.
Inside Lexi, Cambridge and WordNet remain distinct reference providers. Search uses
Cambridge identities; generation uses evidence from both. Consumers use `reference`
handles and do not read either provider's internal data.
Generated `vendor/lexi-ai/content.sqlite` ships with the backend image and is imported
automatically by the migration gate through Lexi's `import_content()`. Compatible
alternative snapshots can be selected with the gate's `--content` option.
Importing content never invokes inference. Setup imports reference and content once,
while API restarts read persisted PostgreSQL data.

## Current API

| Operation | Auth | Result |
| --- | --- | --- |
| `GET /v1/words:search?query=...` | Optional | Native saved-word matches; optional reference entries |
| `GET /v1/words/{word_id}` | Optional | Native complete Word with separate senses |
| `POST /v1/words:batchPreview` | Optional | Up to 30 complete word groups / 500 senses, native examples |
| `GET /v1/me/words/{word_id}` | Required | Viewer progress and Library membership context |
| `POST /v1/me/senses:batchReadContext` | Required | Same bounded viewer projection for up to 100 senses |
| `GET /v1/me/senses/{sense_id}/decks` | Required | Authorized containing-deck overflow |
| `POST /v1/words:generate` | Required | 202 in-memory task status and polling URL |
| `GET /v1/word-tasks/{task_id}` | Required | Current shared status |

Search accepts `include_reference`, default false, and returns one ranked `items`
list of discriminated `WORD` / `REFERENCE` hits. Every item has `match_kind`
(`EXACT`, `PREFIX`, `SUBSTRING`, `FUZZY`) and `matched_surface`. Exact matches include
saved aliases, forms and licensed patterns. Match relevance comes first; within
each class generated words precede reference candidates, followed by matched
surface origin (lemma, alias/alternative, form, pattern) for every match class.
Remaining ties use descending Tantivy score, normalized label, then stable ID.
Search keeps the best match per identity before applying the combined 30-item
default limit. Patterns with slots only produce anchored exact matches. Fuzzy
matching is disabled below three characters; distance is one for 3–5 characters
and two from six characters. References already linked
to a completed word are excluded. The UI preserves the returned order and allows
explicit selection; it does not rerank results. Native batch generation reuses or
generates from the first `EXACT` item, rejecting suggestion-only matches.
Reference entries are selectable reference handles, not saved sense IDs. Do not pass a reference handle as
`sense_id`, collapse all meanings into one learning identity, or fabricate a stable handle.
Missing Word returns `word_not_found`; native invalid search input maps to
`invalid_lexical_query`. Exact native Word/SearchResult fields come from OpenAPI.
Sense responses no longer contain `usage_note`; Dictionary renders examples,
forms, patterns, collocations, register and CEFR metadata from the native contract.

## Search cost and cache boundary

This word search remains native Lexi/Tantivy. It is not the PostgreSQL node
FTS over names/descriptions and does not search Library folder metadata.

`Lexicon.start()` builds one process-local Tantivy index before the API accepts
requests. Search performs no SQL, full rebuild, timed refresh, or result caching.
Every completed word publication updates only that word's documents, removes its
consumed reference documents, commits, and publishes a new `(index, searcher)` reader
snapshot. Existing requests retain the old reader without copying the full index.
Only writers serialize; search readers do not wait on a write lock.

The index stores individual surfaces with their identity and origin. Retrieval follows
match tiers and stops when enough distinct identities are available. It geometrically
increases retrieval when multiple surfaces belong to the same identity. Fuzzy matching
runs inside Tantivy; Python deduplicates retrieved hits and matches head-selected patterns.
Raw surface scores tie within a tier, so retrieval uses a constant score rather than an
extra score-probe query. Pattern matching can inspect more than 30 candidates.

Pycil runs one API process, sharing one Lexicon across HTTP reads and generation tasks.
SQLite artifacts are imported before startup. Direct SQL or another process's writes
require restarting the reader; there is no distributed search synchronization.

Lexical caching is native/shared-content caching. User scheduling state is joined
separately; a Word cache does not contain an author's or viewer's personal progress.
Library preview reads batch native enrichment for the selected page only.

Batch previews use exported lexical contract queries plus one native sense batch, not
one word-detail call per result. Whole requested word groups must fit the 500-sense
bound; oversized input fails `lexical_batch_too_large`, never labels a partial word
complete. At most 2 stored examples per sense. No paid inference or vendor-wheel rewrite.

Private context reads the viewer's state even for senses outside Library, then resolves
Library once for containing canonical decks. Up to 5 readable sources inline, exact
count and overflow page; `editable` distinguishes owner from public read access.
Reference aliases deduplicate, revoked content disappears, existing personal state remains.
Context bounds/work errors fail explicitly, never display a false `In 0 decks` value.
Word denominators use actual selected word senses, not native search hit count. There
is no global POS-aware query, fabricated complete phrasal family or translated/audio data.

## Selected-entry generation

POST fields:

```json
{"reference_id": "<handle-returned-by-native-search>", "target": "bank"}
```

This illustrates the request shape; the placeholder is not a valid handle. Supply a
handle actually returned by the same reference source. The service validates the target
lemma and delegates handle/evidence validation to Lexi
before registering a task; it does not access the private reference store.
The target is the learner's input, not a required output identity. Lexi passes it
with the selected evidence to the LLM, which returns the normalized citation lemma:
for example, `glistening` may produce `glisten`. Validation checks the output schema
and supplied reference IDs; it does not require the lemma or aliases to match the
raw input. The returned lemma is stored unchanged by generation code, including
licensed slots. An existing completed canonical Word is never overwritten.
After inventory normalization, an existing completed Word is reused before enrichment:
Lexi lazily links the selected Cambridge entry through `WordReference` (`word_references`),
returns that Word and removes the resolved reference from search. Repeating the selected
reference needs no inference. Word references map Cambridge entry IDs to Word IDs;
SenseReference separately records Cambridge sense or WordNet synset evidence.

The response contains `task_id`, `status`, nullable `word_id`, `stage`, `error`, and
`status_url`. Poll that URL; a 202 confirms acceptance rather than question readiness.
Task status is shared vocabulary metadata, readable by authenticated callers who know
the ID. It stays in memory until process restart; it is not private user history.

## In-process generation

The API registers an async task keyed by reference identity. Concurrent selections of
that reference receive the same task ID while Word generation runs. The check/register step contains no await. Persisted reference linkage reuses a published Word without inference.
The Assistant submits word strings without reference IDs; these jobs use normalized input
keys and the native `generate_word(target)` exact-search path. Case/spacing variants join
the same input job, and native reference locks still serialize overlapping publication.
The Dictionary's explicit-reference HTTP request is unchanged.

Inventory precedes concurrent enrichment batches of up to eight Senses; committed DONE Words are published to search. Word generation ends SUCCEEDED/READY. It does not generate question banks. Provider concurrency remains 128 and the task deadline 600 seconds. Errors are sanitized, committed lexical content remains, and shutdown cancels/joins owned tasks. A process restart loses task status; an explicit request reuses committed content.

Enrichment rejects examples without valid target markup. Schema failures use the existing
bounded Lexi retries, reporting the latest field errors to the same model while preserving
the original instructions and evidence. Validation remains mandatory; invalid output is
never published and exhausting retries still fails the task.

## Learning boundary

Study preparation selects Senses from scope and personal Memory/Mastery, plans public types/formats, then asks Lexi to retrieve/refill question artifacts. Saved membership and due counts do not depend on existing banks. Typed grading is separate. See [Study](study.md).

Browsing or generating vocabulary does not create personal learning state or activity.

## Sources and tests

- [Vocabulary router](../../../apps/api/pycil/vocabulary/api.py), [generation service](../../../apps/api/pycil/vocabulary/generation.py)
- [vendor provenance guide](../../../vendor/lexi-ai/README.md), [Docker build](../../../apps/api/Dockerfile)
- [Native learning/generation integration](../../../apps/api/tests/integration/test_learning_pipeline.py)

- [Singleflight and concurrency tests](../../../apps/api/tests/integration/test_background_generation.py)
