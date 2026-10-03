# Backend scout and frontend handoff

Verified against the working tree on **2026-10-03**, including the user-authorized
integration fixes. This handoff does not authorize deployment, application data
provisioning, a frontend stack choice, or additional product features.

**Verdict:** the identified backend integration gaps are fixed and verified offline;
frontend implementation can start against the contracts below. Live browser,
identity/provider and application deployment gates remain separate. The backend has
five business modules and **24 business HTTP operations**. There is currently no
`apps/web` or running Docker application
stack. This integration patch includes the verified cache corrections.

## 1. Integration fixes and verification

| Finding | Implemented correction | Verification |
| --- | --- | --- |
| Cross-origin editor | Runtime CORS now permits PUT. | Preflight checks for all five methods, including auth/content-type/idempotency/request-ID headers. |
| Approval reload | Conversation GET uses native graph state, projecting AG-UI messages and pending approval IDs/actions instead of checkpoint internals. | Fresh-runtime HTTP reload, foreign-owner 404, no extra model invocation/debit, HTTP approve/reject and cleared approvals afterward. |
| Image transport | A common Caddy API body cap mirrors **15,000,000 bytes** for stream and JSON handlers. | Real Caddy accepts a 1.2 MB stream body and the exact cap; cap+1 returns 413. Base64/envelope overhead still counts. |
| Stream edge policy | Caddy matches `/v1/assistant`, excludes compression and uses native SSE auto-flush, without `flush_interval -1`. | Real Caddy delivers the first event without waiting for stream completion and cancels upstream on client disconnect. |
| Typed contract | All 21 JSON success responses have models, reusing native lexical/grade dataclasses. OpenAPI declares required/optional Clerk Bearer, shared safe errors and `text/event-stream`. | Existing HTTP flow tests plus full OpenAPI shape/security/error checks across all 24 operations. |
| Obsolete guidance | Current docs describe unpaginated decks and fresh `0001_baseline`; the rewrite checkpoint is explicitly historical. | Source/schema/contract reconciliation; no old-schema upgrade or new migration added. |

Source findings above do not imply that an exhaustive security audit or live
identity/provider/edge verification has been completed.

## 2. Transport, identity and errors

- Application URL prefix: `/v1`. There is no shared `/api` prefix in this backend.
- Protected operations require `Authorization: Bearer <Clerk JWT>`. There is no
  local login/register/token endpoint or application cookie-auth flow.
- The issuer, JWKS, optional audience and first-account identity lookup are
  server-owned. Never put Clerk secret or inference/store credentials in frontend.
- Vocabulary reads and library reads allow anonymous viewers. If an Authorization
  header is supplied, it is validated; an invalid token does not become anonymous.
- IDs: Word/Sense/Question are integers; Pycil node/user/conversation/generation
  IDs are UUID strings. New server IDs use UUIDv7. Client review retry keys only
  need to be valid UUIDs; do not change existing identity contracts.
- Business and API-boundary errors generally have `{"error":"code"}`. Validation
  deliberately has no field-level input echo. UI field validation is client-side.
- `X-Request-ID` is returned and exposed by CORS. A valid incoming UUID is retained;
  otherwise a new UUIDv7 is generated. Preserve it for support, not as a retry key.
- DELETE successes are **204**: do not unconditionally call `response.json()`.
- JSON errors are not guaranteed for edge/network failures. After an SSE response
  starts, errors can be `RUN_ERROR` or an interrupted connection, not a new HTTP
  status. EOF alone is not successful completion.
- Set `ALLOWED_ORIGINS` to the exact frontend origins, including ports. The current
  template does not include a development origin such as `http://localhost:3000`.

## 3. Complete HTTP surface

`Viewer` means anonymous or authenticated; `Actor` means authentication required.

| Module | Operation | Access | Principal contract |
| --- | --- | --- | --- |
| account | `GET /v1/me` | Actor | Profile, resolved settings, effective learning and restriction |
| account | `PATCH /v1/me/settings` | Actor | Two-level preference merge; returns updated profile |
| account | `GET /v1/me/usage` | Actor | Anchored monthly unit allowance/usage |
| library | `GET /v1/library/nodes` | Viewer | Root/folder list, `parent_id`, `after_id` UUID cursor |
| library | `POST /v1/library/nodes` | Actor | Create FOLDER/DECK/REFERENCE; 201 |
| library | `GET /v1/library/nodes/{node_id}` | Viewer | Metadata, safe breadcrumbs, count; DECK adds all Sense previews |
| library | `PUT /v1/library/nodes/{node_id}` | Actor | Atomic final metadata/membership save |
| library | `DELETE /v1/library/nodes/{node_id}` | Actor | Owner-only soft delete; 204 |
| library | `GET /v1/library/nodes/{node_id}/senses` | Viewer | Whole DECK or paginated FOLDER/REFERENCE scope |
| vocabulary | `GET /v1/words/search` | Viewer | Required `query`, optional `include_available=false` |
| vocabulary | `GET /v1/words/{word_id}` | Viewer | Native full lexical Word or 404 |
| vocabulary | `POST /v1/word-generations` | Actor | Selected `available_id` + `target`; 202 |
| vocabulary | `GET /v1/word-generations/{generation_id}` | Actor | Shared generation status |
| study | `POST /v1/study/prepare` | Actor | `{"node_id":"<UUID>"}`; neutral artifacts, no learning writes |
| study | `POST /v1/study/grade` | Actor | Typed-answer diagnostics; requires advanced grading |
| study | `POST /v1/study/reviews` | Actor | Sense rating; required UUID `Idempotency-Key` header |
| study | `GET /v1/study/progress` | Actor | Global or `node_id`-scoped dashboard |
| study | `GET /v1/study/history` | Actor | `days=30`, `after=<event UUID>` |
| assistant | `GET /v1/assistant/models` | Actor | Selectable model IDs/names/vision/efforts |
| assistant | `POST /v1/assistant/conversations` | Actor | `{"title":null}` or title; 201 |
| assistant | `GET /v1/assistant/conversations` | Actor | Newest-first list, paired timestamp/UUID cursor |
| assistant | `GET /v1/assistant/conversations/{identifier}` | Actor | Metadata, native AG-UI messages and persisted pending approvals |
| assistant | `DELETE /v1/assistant/conversations/{identifier}` | Actor | Owned thread/checkpoint deletion; 204 |
| assistant | `POST /v1/assistant` | Actor | Native AG-UI request; SSE stream |

`GET /health` and `GET /ready` are operational and omitted from OpenAPI. Readiness
checks PostgreSQL/Redis; it does not certify inference or identity credentials.

## 4. Account/settings and product limits

Profile fields: `id`, nullable `display_name`, `plan`, `settings`,
`effective_learning`, `learning_restriction`. Settings contain only `locale`,
`timezone`, `translation_language`, and `learning`. Learning contains
`question_types`, `formats`, `questions_per_sense`, `question_budget`,
`show_explanations`.

- PATCH omitted keys stay unchanged; nested learning changes merge one level.
  Explicit null and unknown keys are rejected. Empty PATCH is allowed.
- Locales and translation languages currently support `en`/`vi`; timezone is IANA.
- Current defaults: three questions/Sense, budget 30, all seven question types,
  SINGLE_CHOICE only, explanations enabled. Bounds: K=1–7, budget≤100, budget≥K.
- FREE and PRO both have ASSISTANT; only PRO has ADVANCED_GRADING. FREE attempts to
  select typed formats receive `403 advanced_grading_not_available`.
- Use `effective_learning`, not merely saved preferences. Downgrade can make saved
  typed-only settings infeasible: effective learning becomes null with
  `learning_restriction="infeasible_learning_preferences"`.
- `/me/usage` returns `period_start`, `period_end`, `allowance_units`, `used_units`,
  `remaining_units`. The month is anchored to the account, not calendar-month reset.
- There is no public UI-policy/capabilities endpoint. The implementation must
  explicitly decide how to keep displayed limits/type-format options aligned with
  `config/config.yaml`; do not expose the entire provider configuration as UI data.
- `display_name` is nullable and current provisioning does not populate it from
  Clerk. There is no backend profile-name update route.

## 5. Library editor and navigation

Types are `FOLDER | DECK | REFERENCE`; visibility is `PRIVATE | PUBLIC`.

### Editor writes

Keep a local draft and submit one final save. Example existing DECK PUT:

```json
{
  "name": "Travel",
  "description": "Vocabulary for travelling",
  "parent_id": null,
  "visibility": "PRIVATE",
  "confirm_publication": false,
  "sense_ids": [12, 45, 78]
}
```

- Do not send read-only fields (`id`, `owner_id`, `type`, timestamps, breadcrumbs,
  `reference_id`) in PUT. The schema forbids extras; the node type/target is fixed.
- `name` and `visibility` are required. Description and parent default to null:
  **omitting them clears them**, rather than preserving them as PATCH would.
- Existing DECK PUT requires final `sense_ids`; `[]` explicitly clears membership.
  IDs must be distinct positive integers. Creating a deck can omit membership.
- FOLDER/REFERENCE saves omit `sense_ids`. Creating a REFERENCE requires its target
  `reference_id`; a REFERENCE cannot target another REFERENCE.
- Cap is 200 Senses. Pre-existing larger decks remain readable and permit unchanged
  membership/removal-only saves. Additions leaving the final set above 200 fail.
- New publication/change to PUBLIC requires `confirm_publication=true` or returns
  `409 publication_confirmation_required`. Publishing a folder affects descendant
  access. Prompt for this consequence; do not silently resubmit confirmed writes.
- Writes validate owner, parent, cycles and depth≤20. All fields/membership commit
  together. Later successful save wins; there is no ETag, conflict detection or
  multi-tab draft merge. Re-read after save and invalidate relevant query data.
- Membership is an unordered set, returned sorted by Sense ID, not drag order.
- Soft-deleted folders make their descendant paths unreadable. References remain
  live, not copies; target revocation/deletion can produce 404 for saved references.

### Reads and cursor distinctions

- Library list returns `{nodes, next_after_id}`; page size 50, ascending created
  time/UUID. Root listing combines the viewer's roots and other public roots.
  There is no separate server-side own/public/search filter for library tabs.
- Detail includes safe `breadcrumbs` and `sense_count`. **DECK** also includes
  `senses` for the entire deck; it has no `sense_page` wrapper or Sense cursor.
- DECK `/senses` returns `{senses}`. Nonzero `after_id` fails with
  `422 deck_cursor_not_supported`; do not use infinite scrolling to load a deck.
- FOLDER/REFERENCE `/senses` returns `{senses, next_after_id}`; use the integer Sense
  cursor and limit 50. These scopes deduplicate Senses.
- Preview fields: `sense_id`, `word_id`, `lemma`, `entry_type`, `pos`, `tier`,
  `definition`, `cefr_level`, `register`, `ipa_uk`, `ipa_us`, `learning`.
- `learning` is null anonymously; authenticated state belongs to the viewer, not
  owner. Its fields are `state` (NEW/DUE/NOT_YET_DUE), `mastery` (0–100), `due_at`,
  `last_rating`. Full lexical content comes from the Word route.
- Private ancestor IDs/names are deliberately sanitized. Do not reconstruct hidden
  breadcrumbs from references, cached raw metadata or guesses.

## 6. Vocabulary search and generation

Search returns `{words, available}`. Saved hits contain `word_id`, `lemma`,
`entry_type`, `match_kind`, `matched_surface`. Available hits contain an **opaque**
`available_id`, `display`, `entry_type`; they do not yet supply saved Sense IDs.
Request `include_available=true` when offering generation.

Match kinds: LEMMA, ALIAS, FORM, PATTERN, PREFIX, SUBSTRING, FUZZY. Entry types:
WORD, PHRASAL_VERB, IDIOM, PHRASE, EXPRESSION. Cambridge and Lexi share native
in-memory search; the HTTP result uses the two groups above, not a new `source`
field or Pycil search engine. There is no search cursor/limit parameter here.

- Debounce and discard out-of-order responses. Do not assume SQL ranking or exact
  cross-process visibility at 30 seconds; refresh involves scheduling and rebuilds.
- A saved Word contains `id`, `lemma`, `type`, `generation_state`, `senses`,
  `aliases`, `related`. Senses contain definition/examples/forms/patterns/
  collocations/relations, pronunciation, tier/POS, CEFR/register/usage-note.
- Forms are Sense-scoped (`surface`, `inf`), not generic Word-level licensed forms.
- Generate from a selected handle plus the intended target lemma, not from a search
  query alone. POST response is `{generation_id,status,word_id,stage,error,status_url}`.
- Poll `status_url`: QUEUED → RUNNING → SUCCEEDED/FAILED; automatic retry can return
  to QUEUED. `stage` can be WORD/QUESTION_POOLS/READY; it may be null initially.
- `word_id` can exist before all question banks are ready. Wait for SUCCEEDED for
  the completed generation flow; a saved Word is not proof of prepared questions.
- Generation is shared/idempotent by `(available_id,target)`, not user-private.
  Resubmitting a FAILED selection resets it for retry. No polling owner restriction
  or cancel endpoint exists. Generation does not debit the user's subscription units.
- Worker must be running; API readiness alone does not process queued generation.

## 7. Client-owned learning

Prepare returns `{requested_sense_count, actual_sense_count, actual_question_count,
preferences, bundles}`. A bundle is `{sense, reason, questions}`; each question item
is `{question, format, level, options}`. Counts are actual, not guaranteed to fill
the requested budget. Zero bundles is a valid empty/unready scope result.

- Candidate priority: DUE → NEW → NOT_YET_DUE. Requested Senses are
  `floor(question_budget / questions_per_sense)`. Retrieval is native and batched.
- A native Question has `id`, `sense_id`, `theme_id`, `question_type`, `content`,
  `correct`, `distractors`, `correct_alternatives`, `target_placement`. Options have
  `id`, `content`, `explanation`. Correct answers are intentionally supplied for
  client-owned/offline learning; this is not an anti-cheating examination API.
- `content` is a string **or dialogue entries** `{speaker,text}`; null text is a
  completion slot. Preserve target markup such as `<t inf="base">...</t>` through
  a constrained renderer, not arbitrary HTML injection or blanket tag stripping.
- Formats: SINGLE_CHOICE, SINGLE_WORD, SHORT_ANSWER. Seven question types are
  DEFINITION_TO_WORD, CONTEXT_TO_WORD, CLOZE_TO_WORD, WORD_TO_DEFINITION,
  WORD_TO_USAGE, DIALOGUE_COMPLETION, MEANING_IN_CONTEXT. Levels are integers 1–4.
- Preparation writes no session, answer or memory. Client owns progress within the
  local session, answer collection, question navigation and rating aggregation.
  There are no start/resume/complete-session endpoints to invent.
- Single choice is evaluated locally. `/study/grade` accepts
  `{question_id,format,answer}` for authorized typed formats; it returns native
  diagnostics, **not** a universal numerical score or automatic FSRS rating.
- SingleWord diagnostics: `task_fit`, `spelling_error`, `sense_id`. Definition:
  `sense_id`, `accuracy`, `coverage`. Usage: `used`, `meaning`, `form`, `construction`,
  `collocation`, `appropriacy`. Preserve nullable fields as unknown/not applicable.
- Submit a Sense rating `{sense_id,rating}` with AGAIN/HARD/GOOD/EASY. Persist a UUID
  `Idempotency-Key` with each outbox entry **before** sending; retry with the same
  payload/key. A changed payload with the same key gives `409 review_event_conflict`.
- Review response: `sense_id`, `rating`, `applied`, `accepted_at`, `mastery_after`,
  `due_after`. Early positive ratings are practice (`applied=false`); early AGAIN
  still applies FSRS. Server receipt order/time is authoritative, not client time.
- Refresh Sense learning state, progress and history after accepted review. Do not
  compute the authoritative due date or mastery on the frontend.
- `409 learning_content_changed` means prepare again; do not use a partial bundle.

Progress returns `summary` (total/learned/due), `activity`, `forecast`,
`weakest_senses`, `cefr_distribution`. Activity distinguishes `applied_reviews`
from `practice_events`; weakest records are Sense ID/mastery, not lexical labels.
Global scope includes learned Senses even after removal from decks. Activity and
forecast use the account timezone. History returns `{events,next_after,applied_count}`;
its `applied_count` is computed over the current query, including the cursor filter,
not a stable grand total across pages. Days must be 1–365; page size is 50.

## 8. Assistant transport and approval

Create an owned conversation first. POST `/v1/assistant` uses camelCase native
AG-UI fields; send **one new user message**, not the full chat transcript:

```json
{
  "threadId": "<conversation UUID>",
  "runId": "<new run ID>",
  "messages": [{"id": "<message ID>", "role": "user", "content": "Please help"}],
  "state": {},
  "tools": [],
  "context": [],
  "forwardedProps": {}
}
```

- The server owns persisted history, tools and agent state. Nonempty state/tools/
  context or `parentRunId` is rejected. `forwardedProps` allows only `model_id` and
  `effort`; populate the selector from `/assistant/models`.
- Use a POST streaming client with authorization and AbortController; the native
  browser EventSource GET interface is not this API's request contract.
- Handle AG-UI snapshots, text chunks, tool calls, steps, RUN_ERROR and RUN_FINISHED.
  A RUN_FINISHED with `outcome.type="interrupt"` means awaiting approval, not that
  a mutation succeeded. Its `outcome.interrupts[].id` is the resume ID; current
  action/review data is in `metadata.langgraph.raw`.
- Collection create/update/delete tools require approval and live reauthorization.
  Resume with no messages and exactly one entry:

```json
{
  "threadId": "<conversation UUID>",
  "runId": "<new run ID>",
  "messages": [],
  "resume": [{
    "interruptId": "<current persisted interrupt ID>",
    "status": "resolved",
    "payload": {"decisions": [{"type": "approve"}]}
  }]
}
```

- Supply one approve/reject decision per action, in action order; editing decisions
  is not supported. All-reject does not run a new model call or debit units, even
  when allowance is exhausted. Pending approvals block ordinary new turns.
- Conversation GET returns `state: {messages, pending_approvals}`. Messages use
  native AG-UI roles/fields. Each approval has `interrupt_id`, `action_requests`
  (name/args/description), and `review_configs` (action_name/allowed_decisions).
  Use the persisted ID for resume after reload; do not fabricate one.
- Empty conversations return empty arrays, not a null checkpoint. Reads reconstruct
  native graph state without invoking a model/tool or settling usage. A stream and
  a read can overlap; refresh after turn completion and handle stale approval 409s.
- Raw checkpoint channels, provider message internals and task bookkeeping are not
  part of this HTTP response. Live SSE approval metadata follows native AG-UI;
  REST pending approvals provide the corresponding typed UI projection.
- Conversation pagination returns `{conversations,next_after}` with
  `{updated_at,id}`; send both `after_updated_at` (timezone-aware) and `after_id`.
- One active turn per conversation; simultaneous turn/delete gives
  `409 conversation_busy`. Start limit 20/minute/user; turn timeout 60 seconds.
  Inactive conversation retention is 30 days, performed by the worker.
- Images: inline base64 native `source:{type:"data",mimeType,value}` only, with
  PNG/JPEG/WebP MIME types. No URL fetch, upload route, audio or document support.
  Up to four images, each decoded≤10 MB, subject to the smaller total body budget.
- Completed calls can be settled on cancellation. Aborting or disconnecting does
  not imply free usage, a server rollback, or safe automatic replay of the turn.

## 9. Features not supported by the current surface

Do not implement a backend-dependent control for these without a separate scope
decision: checkout/billing/subscription webhooks, public plan change, account
export/delete, profile editing, conversation rename, media uploads, lexical
translation endpoint, server learning-session persistence, automatic grade-to-rating
mapping, versioned editor merge, global library search or server own/public filters.

`translation_language` is a stored preference, not proof of a translation API.
FREE/PRO models and an internal `change_plan()` exist, but are not a billing system.

## 10. Runtime, cache and verification boundaries

- Runtime/CI: Python 3.14.8; PostgreSQL 18.6; Redis 8.10.2; stock database images.
  Install/build uses the checksummed vendored Lexi wheel, not a sibling checkout.
- Explicit migration order is Lexi → Pycil → native checkpoints. Pycil head is
  **0001_baseline**; it requires an empty public schema. Startup verifies, never
  migrates. Do not run this against surviving old data as an upgrade path.
- Product policy is YAML; deployment addresses/credentials come from environment.
  Host runtime does not auto-load `.env`. Corpus mounts remain read-only.
- Actor/deck Redis caches are optional detached values with TTL 60s, cap 1,000,
  payload≤65,536 bytes. Cache GET uses orjson → validation; SET uses JSON-mode model
  dump → orjson. TTL guard and exclusive stale-score purge are in the working tree.
- Authorization, entitlements, learning memory and accounting are not authorized
  from these caches. Invalidation plus TTL is bounded-staleness behavior, not a
  read-after-write guarantee against every fill race. Do not cache user-sensitive
  client queries across sign-out/account switches.
- CI runs on PRs to main/dev and pushes to main, **not direct pushes to dev**.
  Syntax/config validation of Caddy does not test its correspondence to real routes.

### Latest integration-fix checks

- Full Pycil suite on new disposable PostgreSQL/Redis: **147 passed,
  11 upstream AG-UI/LangGraph warnings, 53.49 seconds**.
- Native persisted approval GET/reload and HTTP resume, including rejection with
  exhausted allowance, are tested with deterministic completions.
- Ruff lint and format passed. OpenAPI generation needs no runtime/database startup;
  typed success/errors and required/optional security cover all 24 operations.
- Caddy configuration validation and real disposable proxy checks passed:
  uncompressed first event (~3.7 ms in this local probe), upstream cancellation,
  exact body cap accepted and cap+1 rejected. This is not a production latency claim.
- Temporary stores/storage removed. No application bootstrap, paid inference,
  Lexi benchmark, frontend generation, commit/push or deployment. No new test files.

Local evidence (not runtime dependencies):

- `/tmp/opencode/pycil-frontend-fixes-tests-20261003.txt`
- `/tmp/opencode/pycil-frontend-edge-results-20261003.json`
- `/tmp/opencode/pycil-frontend-fixed-openapi-20261003.json`

The earlier `pycil-frontend-scout-*`/native-state/OpenAPI files record the
**pre-fix** investigation; they are not current response examples.

### Recommended frontend delivery order

1. Choose same-origin/proxy versus direct cross-origin API access, configure exact
   allowed origins and consume the current typed success/error/SSE contracts.
2. Auth bootstrap, `/me`, settings, common error/request-ID handling.
3. Vocabulary search/detail and asynchronous generation status UI.
4. Library browsing, public/reference states and local-draft atomic editor.
5. Client-owned study renderer/session, typed grading and durable review outbox.
6. Progress/history, then assistant streaming/approval/reload recovery.
7. Browser gates against the actual edge: CORS PUT, large images, first SSE event,
   disconnect/reload, publication confirmation, revocation, duplicate reviews,
   account switching and empty/unready learning content.
