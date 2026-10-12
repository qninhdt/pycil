# Implementation status

Archived record. Current-only baselines and targeted Library mutations supersede the migration/editor contracts below; see [current setup](operations/migrations.md) and [OpenAPI](openapi.json).
Date: 2026-10-06. Backend completion based on `e79a53c`.
The reduced backend contract is implemented; this is **not a deployment announcement**
or production capacity certification. The [execution plan](implementation-plan.md)
records acceptance and external gates.

## Implemented

| Area | Current contract / evidence |
| --- | --- |
| Foundation | Library/Personal/Published placement, closure, quotas, live reference authorization and complete editor preserved |
| Learning persistence | `UserSense` / `user_senses`; one state per user/sense, no source/session attribution |
| Migration | Appended 0003/0004/0005; populated 0001/0002 upgrades preserve state/receipt/settings; historical revisions unchanged |
| Reviews | Ordered 1-100-result batch, UUID key, canonical SHA-256, sorted locks, atomic original receipt and frozen daily counts |
| Scheduling | NEW/DUE/AGAIN apply native FSRS; early positive practice mutates no state; replay/rollback/concurrency tested |
| Prepare | NEW/DUE/AUTO, maximum senses, persisted settings/entitlement, repeatable-read readiness and short-circuiting |
| Reporting | Exact unique counts/coverage/recency, joint summaries and shared physical/logical work bounds/deadlines |
| Activity / schedule | Frozen accepted dates, zero-filled grids, lifetime/current streak and independent future due dates |
| Browsing | Bound opaque cursors, strict queries/limits, literal lemma search, review/lemma ordering, examples and source overflow |
| Search | Weighted generated PostgreSQL FTS/GIN, scoped search and public Discovery with authoritative path checks |
| Dictionary | Native search unchanged, bounded complete word groups and private progress/membership/deck overflow |
| Profile | Optional unique canonical ASCII handle/bio, concurrent conflict handling, rename lookup, public-safe joined date |
| Assistant | Thin summary/search/context/list reads; approval, publication, editor and AG-UI protections retained |
| Cleanup | No scalar review parser, budget/mastery/weakest/dashboard/history or old cursor aliases |
| FE readiness | Safe learning options, exported 37-operation OpenAPI and English screen/error/scenario/host handoff |
| Test tooling | Automatically owned disposable stores; no application `.env` or manual test URLs |

Old events use the validated upgrade-time timezone because event-time timezone was
not stored. New accepted dates never regroup. 0003 refuses lossy downgrade; recovery
needs a verified pre-upgrade backup plus compatible old release.

## Verification

The [verification record](verification.md) is authoritative for final counts/checks.
The final full suite passed **240 tests**, with one opt-in benchmark skipped and
11 upstream LangGraph deprecation warnings. Lint/format and 103 unit tests passed.

Small/medium matrices passed with 200,000 reachable memberships, native ready banks,
reference cycles/aliases, 100,000 medium states/receipts and overlapping writes.
5-card and 50-card summaries both use four SELECTs. Full SQL plans and smoke-load
limits are described in [performance evidence](operations/performance.md).

Fresh/repeated ordered migration, populated upgrades, Alembic drift, process restart,
cache failure, real SQL cancellation, revocation and concurrency use real disposable
stores. Runtime/test Compose, deployment shell, Caddy, wheel and OpenAPI checks are
separate from deployment or artifact promotion.

## External gates, not missing backend features

1. **Capacity:** large 100k-user / 1m-node / 10m-state/receipt tier needs separate
   resource approval. Deployment hardware and latency/QPS/error thresholds were not
   supplied. Local short-run percentiles do not certify a long-duration production SLA.
2. **FE:** local `apps/web` starter/showcase work is not an approved implemented
   Pycil API client. It was not overwritten or silently selected as the target.
   Agree product integration and recall-rating UI; Correct/Incorrect does not define
   GOOD/EASY. Backend handoff is complete independently of those decisions.
3. **Live host:** matching Clerk, reference corpus, generated vocabulary/banks,
   inference/decision providers, worker and CORS need approved host inputs. Native
   deterministic fixtures prove contracts, not real provider readiness.
4. **Release:** no production migration or deployment is implied.
   Quiesce writers/assistant runs, rehearse restore and deploy matching breaking
   contracts only after separate approval.

Star/Pin, difficult/bookmark, tags, translations, country, Import, TTS, courses,
recommendations and session/time/accuracy metrics remain deliberately absent.
Legacy documentation cleanup and unrelated user work are outside this backend commit.

## Frontend integration update — 2026-10-08

The user authorized `apps/web` product integration and changes to both frontend and
backend. Four targeted Library operations extend the generated contract to 41
operations: metadata PATCH, sense delta action, move and atomic subtree copy. Legacy
PUT/editor callers are preserved. Discovery, publication consent, saved public
references and source overflow are connected in the frontend.

The earlier counts above describe the 2026-10-06 backend verification only. Current
contract/unit checks and live browser execution have separate evidence in the
frontend E2E plan (archived, removed). Real store/browser/provider
execution must not be inferred from those historical counts.

## Custom-action naming update — 2026-10-08

All 13 custom methods use `resource:verb` with camelCase action names; see
[API conventions](api-conventions.md#custom-actions) and the regenerated
[OpenAPI](openapi.json). Frontend callers, browser fixtures, backend tests and
Caddy's Assistant SSE matcher use the same URLs. Sense deltas now use POST;
handle lookup uses a required query parameter. Old action URLs have no aliases.

Validation: all backend tests passed against managed disposable PostgreSQL/Redis
(276 passed, one opt-in benchmark skipped, 11 upstream LangGraph warnings).
Backend Ruff lint/format, frontend production build and Caddy validation passed.
Focused frontend adapters and three Assistant browser fixtures passed. These
browser fixtures intercept API responses; they do not establish live Clerk or
provider success. Live full-stack execution remains recorded separately in the
frontend E2E plan (archived, removed).
