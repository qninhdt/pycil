# Vocabulary, lexical search, and generation

## Responsibility

Lexi owns the shared lexical model and native APIs for words, senses, previews, question
banks, search, generation, and grading. Pycil exposes a narrow HTTP surface and owns
the durable selected-entry generation queue. There is no copied Pycil dictionary model,
per-user word copy, or bespoke question-store service.

The dependency is the reviewed local wheel under `vendor/lexi-ai`, verified with
checksums and provenance. The external Cambridge SQLite file is a reference source,
not the application PostgreSQL database. Generation also needs the WordNet corpus;
the container installs and verifies it during build.

## Current API

| Operation | Auth | Result |
| --- | --- | --- |
| `GET /v1/words:search?query=...` | Optional | Native saved-word matches; optional available reference entries |
| `GET /v1/words/{word_id}` | Optional | Native complete Word with separate senses |
| `POST /v1/words:batchPreview` | Optional | Up to 30 complete word groups / 500 senses, native examples |
| `GET /v1/me/words/{word_id}` | Required | Viewer progress and Library membership context |
| `POST /v1/me/senses:batchReadContext` | Required | Same bounded viewer projection for up to 100 senses |
| `GET /v1/me/senses/{sense_id}/decks` | Required | Authorized containing-deck overflow |
| `POST /v1/word-generations` | Required | 202 shared request status and polling URL |
| `GET /v1/word-generations/{generation_id}` | Required | Current shared status |

Search accepts `include_available`, default false. Available entries are separately
selectable reference handles, not saved sense IDs. Do not pass an available handle as
`sense_id`, collapse all meanings into one learning identity, or fabricate a stable handle.
Missing Word returns `word_not_found`; native invalid search input maps to
`invalid_lexical_query`. Exact native Word/SearchResult fields come from OpenAPI.

## Search cost and cache boundary

This word search remains native Lexi/Tantivy. It is not the PostgreSQL node
FTS over names/descriptions and does not search Library folder metadata.

Lexi reload builds a process-local index from the full published lexical projection.
Cold/reload work therefore depends on the dictionary, even when a learner later uses
a small Library. Do not call this scope-local constant-time search or infer a capacity
number from the Library's scope guard. API and worker both initialize Lexi resources.

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
{"available_id": "<handle-returned-by-native-search>", "target": "bank"}
```

This illustrates the request shape; the placeholder is not a valid handle. Supply a
handle actually returned by the same reference source. The service decodes it, validates
the target lemma, and checks that the selected reference entry has senses before queuing.

The response contains `generation_id`, `status`, nullable `word_id`, `stage`, `error`,
and `status_url`. Poll `status_url`; a 202 only confirms a queued/reused request, not
ready learning questions. There is no generation-specific SSE endpoint.

Rows are globally unique on `(available_id, target)` and have no owner ID. Different
users requesting the same pair reuse the same job, and any authenticated caller may
read a known job's status. This is intentional shared vocabulary, not private user
generation history. Do not describe owner-only job authorization that does not exist.

Existing QUEUED/RUNNING/SUCCEEDED requests return their current state. Resubmitting a
FAILED request resets attempts and queues it again. Ordinary submission does not debit
the user's assistant allowance; it can nevertheless cause paid provider work in the worker.

## Worker execution and recovery

```text
QUEUED -> RUNNING (WORD)
       -> RUNNING (QUESTION_POOLS)
       -> SUCCEEDED (READY)
failure -> QUEUED with retry delay, or FAILED
```

The owner recovers interrupted RUNNING rows and exhausted queued rows before polling.
Claim uses an eligible-time/status query, ordering by next attempt/creation/ID, with
`FOR UPDATE SKIP LOCKED`. It increments attempts and marks RUNNING in a short transaction;
provider work is not done while holding that row transaction.

Generation has three sequential phases: one inventory request, concurrent enrichment
for every inventory sense, then concurrent question generation for every empty
sense/type bank. Lexi enrichment has no four-request cap. The worker launches all
missing pairs together, waits for them, and cancels/joins pending tasks on cancellation,
deadline or nonretryable failure. Provider rate limits and transport/database pools
can still constrain actual throughput. Execution records `word_id` after enrichment
publication and reads existing coverage in bounded batches. Defaults target
8 questions/type and 5 examples; valid batches may contain fewer or more. Each
question still needs the configured 3 distractors. Known generated labels accept
either case, invalid examples/questions are filtered individually, and canonical
duplicates are removed before persistence. Existing nonempty banks are preserved
through recovery without quota-driven calls.

Each attempt has a 600-second timeout and at most 3 automatic word-generation attempts.
Transient word failures requeue after 5 seconds; invalid selection, credentials,
refusals and other nonretryable errors fail immediately. Native question inference
has its own bounded retry budget. Exhausted retryable question errors leave other
banks available and finish with `SUCCEEDED`, stage `PARTIAL`, and sanitized error
`question_pools_incomplete`. Deadline expiry after word publication also preserves
that partial result. `READY` means every sense/type has usable questions, not quota
completion. Partial publication does not guarantee readiness for every study setting.
Cancellation intentionally leaves RUNNING for recovery by the next exclusive owner.

The worker periodically checks the PostgreSQL coordination connection's backend PID.
Lost ownership must stop execution, not reconnect silently and continue as a second
owner. Generation writes/coverage can survive retries through native Lexi behavior;
they are not one atomic application transaction with the queue.

## Learning-readiness boundary

Word visibility, saved deck membership, and question readiness are distinct. A saved
sense may be Due yet lack enough eligible questions for the chosen preferences.
Study prepare skips unready senses or reports a bank change; it does not enqueue
generation automatically. Grading is a separate explicit native call.

This module does not track sessions, modify personal FSRS state, or create Home tracking
when dictionary content is merely viewed or generated.

## Sources and tests

- [Vocabulary router](../../../apps/api/pycil/vocabulary/api.py), [generation service](../../../apps/api/pycil/vocabulary/generation.py), [queue model](../../../apps/api/pycil/vocabulary/models.py)
- [Worker](../../../apps/api/pycil/worker.py), [vendor provenance guide](../../../vendor/lexi-ai/README.md), [Docker build](../../../apps/api/Dockerfile)
- [Native learning/generation integration](../../../apps/api/tests/integration/test_learning_pipeline.py)
