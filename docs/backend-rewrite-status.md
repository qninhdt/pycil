# Backend rewrite — execution checkpoint

> **Historical checkpoint, superseded on 2026-10-03.** The execution status,
> migration versions, infrastructure and route descriptions below are retained as
> dated evidence, not current operator instructions. Current source uses fresh
> `0001_baseline`, PostgreSQL 18, and `POST /v1/assistant`; see
> [README](../README.md) and [the frontend contract](frontend-backend-contract.md).
> The Docker reset and earlier delivery were completed subsequently. The current
> application stack is not provisioned; current cache/integration follow-up is
> documented in the frontend contract. Do not run the historical cutover/reset
> instructions below.

Updated: 2026-10-02. **Implementation and disposable verification pass; application
cutover/reset remains blocked on exact development-target confirmation.** All
changes are uncommitted/unpushed. No live stack was stopped or restarted.

Authoritative contract: `/tmp/opencode/pycil-study-lexi-redesign-plan-20261002.md`
(revision 3). Historical `docs/design/`, plans, journals and analysis reports are
not current operator instructions. Current architecture/testing docs are reconciled.

## Phase status

| Phase | Outcome |
| --- | --- |
| 0 — archive | 244 files verified byte-for-byte; dirty/untracked/staged work preserved externally |
| 1 — Lexi enums | Scoped canonical enums/DTO/storage/dispatch and forward migration; full PostgreSQL-enabled suite passes |
| 2 — bootstrap | Import-safe runtime, validated YAML, fresh frozen Pycil schema, explicit ordered migrations and safe HTTP boundaries |
| 3 — account | Signed Clerk identity/subject lifecycle, one JSONB preference PATCH, export/delete, configured plans/units/admission/settlement |
| 4 — library | Owner mutations, public/inherited reads, live references/revocation, private breadcrumbs, bounded tree/membership/pagination |
| 5 — generation | Unique selected-entry requests, shared reuse, singleton executing worker, finite retries/recovery, missing-only native bank fill |
| 6 — preparation/grading | Complete K-distinct-type bundles, due/new/future ordering, typed-only feasibility, native diagnostics/nulls and offline artifacts |
| 7 — rating/progress | Native FSRS, all twelve eligibility cases, practice immutability, short User lock/idempotency log, scoped/global/history projections |
| 8 — assistant | Native graph/checkpointer/AG-UI HITL, live tool authorization, bounded input/admission, cancellation settlement and wired retention |
| 9 — wiring/gates | Locked local wheel, Docker/Compose/env/Makefile/CI/docs reconciled; build/process/container gates pass; real application reset not done |

Only five business modules survive, with minimal root infrastructure and one
`worker.py`. No archived implementation, tests, fixtures or helpers were copied.
Archived settings implementations were not consulted. No backend learning sessions,
rounds, exposure/result records, resume/completion policy or frontend rating rules
were added. `apps/web` remains intentionally absent.

## Verified behavior

- Schema owners: Pycil `public`, Lexi `lexi`, assistant `checkpoints`. Explicit gate:
  **Lexi → Pycil → native checkpoint setup → verification**. Runtime only verifies;
  no import-time YAML/connections or runtime migration/repair. Nonempty public
  schema refusal, FK enforcement, repeated installation and metadata drift pass.
- User settings are one JSONB object, read via `/v1/me`, patched only through
  `/v1/me/settings`. Defaults/read-only usage do not create durable rows. Native
  enum values are uppercase, difficulty levels are strict integers 1–4.
- Shared selected `(available_id, target)` generation has no search or unit debit.
  Worker fills all seven neutral banks to eight/type/Sense; append-before-status
  cancellation/recovery recounts and fills only missing content without duplicates.
- Preparation writes no learning state and returns actual A×K counts. Tests cover
  due/new/future priority, K=1/max K, nonmultiple budget, empty/unready scopes,
  typed-only entitlement and intact native dialogue/options/keys.
- Grading returns native SingleWord/Definition/Usage diagnostics and nulls. Missing
  resource/unsupported pair/blank input are errors, not fabricated scores. Free
  rejects typed grading; no advanced-grading tariff or memory mutation exists.
- New/due all ratings apply; early AGAIN applies native FSRS; early positives log
  practice with every memory column unchanged and zero scheduler calls. Equality
  at due time, floor-day boundaries, same-day repeat eligibility, identical concurrent
  retries and cross-Sense changed-payload conflict pass.
- Progress deduplicates deck membership, includes globally learned Senses after
  membership removal, keeps scoped counts local, splits applied/practice activity,
  and uses account timezone for activity/forecast days. Tied-time history pagination,
  user isolation, weakest stability projection and native CEFR distribution pass.
- Assistant ownership/checkpoint persistence/approval rejection/reauthorization,
  active-turn delete/retention protection, native image-part validation, bounds,
  cancellation/disconnect cleanup and completed-call settlement pass. Rejection
  invokes no new model call/debit. Inline native image data only; no remote fetch.

## Verification evidence

| Gate | Actual result | Output |
| --- | --- | --- |
| Pycil full fresh suite, locked wheel | **130 passed**, no skips, 8 upstream deprecation warnings | `/tmp/opencode/pycil-final-130.txt` |
| Lexi full PostgreSQL-required suite | **668 passed**, no skips | `/tmp/opencode/lexi-pg-suite-final.txt` |
| Lexi offline suite | **616 passed, 52 skipped** (superseded for PG gates by row above) | `/tmp/opencode/lexi-suite-final-check.txt` |
| Pycil Ruff lint/format | passed; 61 files formatted | current source/migrations/tests |
| Lexi Ruff lint/format and diff whitespace | passed; 104 files formatted | source/benchmarks/tests |
| Docker locked production build | passed, wheel hash verified, nonroot runtime | `/tmp/opencode/pycil-docker-build-verified-2.txt` |
| Compose/Caddy | configuration validation passed using dummy inputs, no local secret output | local validation commands |
| Actual host API/worker restarts | passed inside full suite | `tests/system/test_process_restart.py` |
| Disposable image runtime | repeated ordered migration, worker check/once, API readiness/restart passed | `/tmp/opencode/pycil-container-smoke.txt` |
| Local wheel reproducibility | second build byte-identical; SHA256SUMS verified | `vendor/lexi-ai/provenance.json` |

The eight warnings are from upstream AG-UI calling LangGraph's deprecated
`get_config_jsonschema`; no native API shim was introduced to hide them.

Test services owned by the rewrite: `pycil-rewrite-test-pg-20261002`, loopback
32769, administration DB `rewrite_test`; Redis `pycil-rewrite-test-redis-20261002`,
loopback 32770, DB 15. Each fixture creates/drops only `pycil_test_<uuid>` and removes
only exact owned Redis keys, never a shared flush. Container smoke used
`pycil_test_75974fbc21f145feabc022db3fca2988` and removed it after closing resources.

```sh
# apps/api
uv sync --locked
PYCIL_TEST_DB_URL=postgresql+asyncpg://test:test@127.0.0.1:32769/rewrite_test \
PYCIL_TEST_REDIS_URL=redis://127.0.0.1:32770/15 \
uv run --locked pytest tests -q --tb=short
uv run --locked ruff check pycil migrations tests
uv run --locked ruff format --check pycil migrations tests

# lexi-ai (the reviewed sibling source, not Pycil's runtime dependency)
LEXI_REQUIRE_PG=1 \
LEXI_TEST_PG_URL=postgresql+asyncpg://test:test@127.0.0.1:32769/rewrite_test \
.venv/bin/python -m pytest tests -q --tb=short
```

## Reproducible dependency and operator wiring

`vendor/lexi-ai` contains the **unpublished local** `0.1.0+pycil.20261002` wheel,
SHA256SUMS and per-source-input provenance. The version suffix is applied only to
the detached build staging tree; Lexi checkout/version/tag remain unchanged.
`scripts/package-lexi.py` refuses changed artifact bytes unless explicitly replaced.
`apps/api/uv.lock` and Docker install the same wheel without author-home/sibling
dependencies. `.gitignore` explicitly admits this artifact and the assistant prompt.

One image runs API/worker/migration; migration is a one-shot prerequisite. Compose
preserves the existing PostgreSQL 16 volume layout; no major-version upgrade/reset
is implied. Readiness is `/ready`, and Caddy streams conversation `/turns` without
compression/buffering. Secrets/addresses are env-owned; all product policy is YAML.
Removed frontend/old worker targets and obsolete restore/failure rehearsals. Exact
script bytes were separately verified at `/tmp/opencode/pycil-obsolete-wiring-20261002/`.
Deploy script requires separate approval, immutable image and verified backup;
failed migrations never pretend an image rollback reverses schema changes.

## Preserved archive and library baseline

Archive: `/tmp/opencode/pycil-before-rewrite-20261002T095821Z/`.
`source.tar.gz` SHA-256:
`37def3c11eee1992cdb3e83c11c916387ccff1abde5cd9cbd4e01eb2602056b1`.
Manifest/VERIFIED/originals/staged records remain intact; retain until explicit
authorization to remove. Secrets/environments/reference/evidence were excluded.

Lexi `v0.1.0` peeled commit remains
`2367bb6871486f9718cbf219b03bc1084a959c71`; published baseline SHA-256 remains
`a7261b2c2f188dc85be2241876003e6f2da68bf9d4c9dc30972e47a5281235d3`.
Retained benchmark ingestion adapts detached copies only; no historical data was
rewritten, no benchmark rerun or library publication occurred.

## Unit policy and accepted limits

FREE=1,000,000 and PRO=10,000,000 units/month. Historical model weights carried
forward: input=0.30, output=2.50, cached read=0.075 units/token. These are **not newly
verified provider prices**. Cache-write weight is unknown and remains `null`;
no invented advanced-grading charge. Offline rating events use receipt order/time;
client outbox loss can lose unfinished work, random banks can repeat questions,
and an in-flight provider call is at-least-once under process failure.

## Remaining blocker and next action

Environment points to candidate `127.0.0.1:5434/pycil`, with running
`pycil-api-1`, `pycil-worker-1`, PostgreSQL 16 and Redis. A configured address/running
stack is **not proof that it is the exact approved disposable development target**.
No service was stopped, application schema reset, Redis namespace cleared or live
restart performed. Confirm that exact target and named writers may be reset before
cutover; preserve reference corpus, credentials, retained evidence and unrelated
services. Then run the ordered gate and repeat deterministic smoke checks there.

No paid inference, benchmark rerun, push/merge, publication, deployment, release/tag
mutation or application reset occurred. Any release also requires rotating the
previously exposed provider credential and resolving the separately recorded NLTK
advisory/publication authorization; those are not silently claimed complete here.
