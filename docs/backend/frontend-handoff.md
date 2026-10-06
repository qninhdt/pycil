# Frontend integration handoff

This backend tranche supplies real contracts, not a new FE framework or app. Local
`apps/web` starter/showcase material was not overwritten or chosen as the product
integration target without agreement.
The checked-out API exposes 37 operations. Use `/openapi.json` for exact native
Lexi/AG-UI types, nullable fields and enums; this guide specifies usage and semantics.
The backend contract is not deployed automatically.

The [exported contract](openapi.json) can be regenerated with `make openapi`, without
stores, runtime `.env`, authentication credentials or provider startup. Run the concrete
scenario fixtures with:

```sh
python scripts/test_api.py tests/integration/test_completion.py tests/integration/test_learning_pipeline.py tests/integration/test_progress.py -q
```

These initialize native lexical rows/banks, owned/public placements and user states in
automatically owned disposable databases. They do not create a persistent demo account
on a live host; a real FE deployment must provision its own explicitly approved data.

## Integration-host readiness

- Matching API/client breaking contract and migration head `0005_profile_handle_bio`.
- PostgreSQL, Redis, Lexi/checkpoint schemas ready; actual Cambridge artifact installed.
- Clerk JWT from the configured issuer/audience; bearer tokens, not emails or user IDs.
- Explicit allowed FE origin. CORS accepts Authorization, Content-Type,
  Idempotency-Key and X-Request-ID; responses expose request correlation ID.
- Vocabulary/questions actually generated and suitable for saved preferences. A saved
  sense or Due count does not imply a ready bank. Empty prepare is a valid outcome.
- Generation requires the worker, WordNet and real configured inference providers.
  Deterministic integration fixtures do not establish real provider readiness.
- Pro typed grading requires current entitlement and configured decision/fallback
  services. Multiple-choice uses generated answer keys; never call grade for it.

No live provider calls, production migration or deployment were performed here.

## Screen/data matrix

| Retained screen/control | Real data/action | Honest limitations |
| --- | --- | --- |
| Sidebar/account dropdown | `GET /v1/me`: root IDs, handle/bio, plan, learning options | No Starred, tags or fabricated profile name |
| Home overview | `GET /v1/study/progress` | Library reachability only, studied coverage not mastery |
| Home activity/streak | `GET /v1/study/activity` | Accepted sense events, not sessions/minutes/accuracy |
| Upcoming reviews | `GET /v1/study/review-schedule` | Future current due dates, not prediction |
| Library/folder cards | `GET /v1/nodes?parent_id=...&include=summary` | One joint card read; budgets can reject enrichment |
| Folder/deck word table | `/nodes/{id}/senses`: state/q/sort/include | Sources confined to scope; native CEFR retained, no topic tags |
| Folder search | `/nodes/{id}/search?q=...` | Name/description token FTS, no fuzzy/autocomplete promise |
| New folder/deck/reference | Node POST | Creation is not universally idempotent |
| Deck edit/add meanings | GET `/editor`, local union/selection, PUT final set | Never replace full deck from one browse page |
| Publish/unpublish | PUT destination + explicit confirmation | Canonical move; retained Personal reference optional |
| Discovery | `/discovery/nodes`, optional q/type/owner/include | No categories/popularity/learners/recommendations |
| Author public profile/tree | `/users/{id}` or by-handle, public Published node ID | No private settings/progress/activity/root IDs |
| Self profile edit | PATCH `/me/profile` handle/bio | No country/avatar/display-name write or identity sync |
| Dictionary search | `/words/search?query=...&include_available=true` | Native hits; no invented global POS count/paging |
| Search/add-word groups | POST `/words/previews` | <=30 words / <=500 senses, fail if incomplete |
| Dictionary word | GET `/words/{id}` plus GET `/me/words/{id}` | Shared native content separate from private viewer state |
| Membership/progress badges | POST `/me/senses/context` | <=100 senses; inline source limit and explicit overflow |
| Learn / Review / practice | POST prepare NEW / DUE / AUTO | <=100 questions; client-local session |
| Flashcards | Scoped senses with `include=examples` | Flip/shuffle/viewing adds no activity |
| Completion | One atomic reviews batch + retained UUID/body | Recall rating is not inferred from Correct/Incorrect |
| Assistant | Existing models/conversation/state/native SSE | Explicit approval, no uncertain blind mutation retry |

Remove/hide deferred Star/Pin, difficult/bookmark, tags, translation, Import, TTS,
courses, recommendations, country and session/time/accuracy metrics. No mocks to fill them.

## Paging and counts

Use `cursor`/`next_cursor`, opaque and <=2,048 characters, unchanged. Default limit 50,
maximum 100. Reuse the same viewer/scope/query/state/sort; mismatches return
`invalid_cursor`. Dates are ISO and times UTC offsets. Refresh after edit/review;
there is no persistent snapshot guarantee. Sense tokens freeze classification cutoff.
Never use old `after_id`/`after`/conversation timestamp query fields.

Counts are exact unique senses in the selected scope: total=new+studied,
studied=due+not_due. Parent counts are not overlapping child sums. Guests have null
personal counts; empty coverage is null. `last_studied_at` means latest applied review
of a current member sense anywhere, not a source session or latest early practice.

Folder display uses a bounded child request with inline summary and independent parent
summary if needed. Mixed cards use one POST `/study/summaries` body `node_ids`; maximum
50, one cutoff/deadline/budget. Never send one progress request per card. A `limit=100`
metadata page may need summaries split into <=50 with user-controlled loading; do not
pretend page-larger-than-summary bounds is one unbounded operation.

Senses accept ALL/NEW/DUE/NOT_YET_DUE, literal case-insensitive lemma substring `q`,
SENSE_ID_ASC/LEMMA_ASC/LAST_REVIEWED_DESC. Personal filters/review sort require sign-in.
`include=examples,sources` adds up to 2 native examples and 5 unique canonical decks,
source count/more flag. Overflow `/nodes/{id}/senses/{sense_id}/sources` remains scoped.
Private containing Library deck overflow is `/me/senses/{sense_id}/decks`.

## Complete request examples

IDs below illustrate shape; obtain actual IDs from returned lexical/node objects.

```json
{"learning":{"max_sense_count":10,"questions_per_sense":3,"show_explanations":true}}
```

PATCH `/me/settings` merges known fields; null is invalid. `/me.learning_options`
provides supported pairs, limits and current typed-grading entitlement. No secret
provider configuration or country is present.

```json
{"handle":"ninh","bio":"Learning English every day."}
```

PATCH `/me/profile`: handle canonical ASCII lowercase, 3-30 characters starting with
a letter; unique. Omission preserves fields; bio null clears, max 500 characters.
Established handle cannot be cleared; rename replaces old handle lookup, UUID stays.

```json
{"node_id":"00000000-0000-0000-0000-000000000001","selection":"NEW","max_sense_count":10}
```

POST `/study/prepare`: maximum is an upper bound. Default AUTO and saved maximum.
NEW never fills with studied; DUE never fills with NEW. Response has actual counts,
effective preferences, native sense/question artifacts, shuffled options and reasons.
No session ID or progress write. Local draft carries index/answers/shuffle/resume.

```json
{"results":[{"sense_id":123,"rating":"GOOD"},{"sense_id":456,"rating":"AGAIN"}]}
```

POST `/study/reviews` with UUID `Idempotency-Key`. 1-100 distinct strict positive IDs.
One final explicit recall rating per sense (AGAIN/HARD/GOOD/EASY). Freeze ordered body
and key in durable client-local storage **before first request**. Unknown network
outcome stays uncertain; retry exactly. New key means new accepted practice, not retry.

```json
{
  "accepted_at":"2026-10-06T10:00:00Z",
  "activity_day":"2026-10-06",
  "results":[
    {"sense_id":123,"rating":"GOOD","applied":true,"accepted_at":"2026-10-06T10:00:00Z","due_after":"2026-10-07T10:00:00Z"}
  ]
}
```

Illustrative original-result response; actual due-after comes from native FSRS.
New/due/AGAIN apply scheduling. Early positive practice has `applied=false` and leaves
all state fields unchanged, but counts activity. Same-key replay returns this original
result even after later learning/timezone changes. Source revocation does not block
already known lexical result submission or reopen the source.

```json
{"node_ids":["00000000-0000-0000-0000-000000000001"]}
```

POST `/study/summaries` returns a list of Summary objects, no raw lexical payloads.

```json
{"word_ids":[1,2]}
```

POST `/words/previews` returns complete native sense groups/examples for the requested
bounded words. Select-all must use the full group, not a truncated search response.
Dictionary private context is independent: no public artifact contains viewer state.

```json
{"sense_ids":[123,456]}
```

POST `/me/senses/context`: learning state/due/applied-review time and readable Library
decks/editability/count/more. Learned-but-untracked senses retain state with no sources.
Lookup never creates progress or Library membership. Keep modal selections local across
search/filter changes; load full editor and union once for save.

## Error actions

Errors use `{error: code}` and X-Request-ID, not reflected answers/credentials.

| Error | FE action |
| --- | --- |
| 401 authentication_required / invalid_credentials | Authenticate or refresh identity; don't fall back to guest with bad token |
| 403 advanced_grading_not_available | Offer allowed formats/plan action, never fake grade |
| 404 node_not_found / reference_unavailable | Stop access, show unavailable; no cached grant |
| 409 review_batch_conflict | Recover stored original key/body; changed results need a new logical submission |
| 409 handle_unavailable | Choose another handle |
| 409 learning_content_changed | Re-prepare/refresh; do not submit invented bank data |
| 422 invalid_cursor | Refresh traversal from first page |
| 422 invalid_preferences / invalid_preparation | Correct K/maximum/type/format combination |
| 422 scope_too_large | Select smaller scope, or metadata-only cards; no partial counts |
| 422 lexical_batch_too_large / context_too_large | Split IDs / load bounded sense selection |
| 503 scope_timeout / query_timeout | Honest retryable read failure; not empty success |
| Uncertain review transport failure | Retry identical frozen key/body; never invent confirmed completion |

Create/save/publish/assistant do not inherit review idempotency. Inspect uncertain
mutation state before retrying. A 200 SSE header does not mean an assistant turn finished.

## Scenario evidence and remaining FE decisions

`tests/integration/test_completion.py` exercises real API/store profile/search/modal,
context/revocation/pagination and uncertain batch replay. `test_learning_pipeline.py`
uses native Lexi generation/storage with deterministic external completion only at the
provider boundary for ready/new/due/early/no-ready-bank cases. `test_progress.py`
checks empty dates/timezone/streak/schedule; migration tests preserve populated data.
Use these disposable scenario setups, never application data or paid-provider fixtures.

Before FE completion, explicitly choose recall-rating UI/aggregation; generated answer
feedback does not define a GOOD/EASY rating. Continue/recent lookup may be same-device
local state; no server cross-device session or lookup telemetry exists. Obtain the FE
target and host credentials/artifacts before live browser acceptance.
