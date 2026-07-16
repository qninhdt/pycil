# System Architecture

**Stack:** FastAPI + SQLModel + Alembic (Python 3.12), `uv` package management.
**Status:** Python greenfield migration (`plans/260705-0032-python-greenfield-migration/`)
— backend phases complete. See
[project-roadmap.md](./project-roadmap.md) for exact phase status and known gaps.

This is a backend-only repository (API + worker + shared Python). It replaces
the prior Go/ent/chi direction and the original single-DB Python MVP described
in `docs/project-changelog.md`'s pre-migration entries. Billing, gamification,
admin dashboard, ELO, SSE, chat, translation/TTS, and the frontend were all
removed — this doc describes only what exists on disk today.

## Overview

Pycil is a vocabulary learning app built around three ideas:

1. **Two-database boundary.** Pycil never stores dictionary content (words,
   senses, questions). That's the internalized `lexi-ai` library's job, backed
   by its own database. Pycil stores only user state (accounts, folder/deck
   hierarchy, FSRS learning stats) and references lexi content by opaque
   integer `sense_id`/`question_id` — no cross-DB foreign keys, no joins.
2. **Ports & Adapters for lexi-ai.** All access to lexi-ai goes through a
   `LexiClient` Protocol. The only implementation today is in-process
   (lexi-ai runs in the same Python process); the port exists so a future
   gRPC split doesn't touch callers.
3. **FSRS-4.5 spaced repetition**, replacing the old ELO scheduler. A single
   binary grade (correct/wrong) drives stability/difficulty updates; mastery
   is a saturating function of stability.

## Topology

```
services (docker-compose.yml):
  postgres     — pycil's own DB (9 tables, see "Two-Database Boundary")
  redis        — session/job/queue state (arq broker + ephemeral session data)
  centrifugo   — realtime pub/sub (v5, HTTP API on :8000, exposed on :8001)
  migrate      — one-shot `alembic upgrade head`; api/worker depend_on this
                 completing successfully before they start
  api          — FastAPI, port 8000
  worker       — arq, four jobs plus pending-grade reconciliation cron; shares api package + lexi-ai
  backup       — profile-gated (`--profile backup`), restic-based pg_dump backup
```

This is a backend-only stack — there is **no Caddy service and no web/frontend
service** in `docker-compose.yml`. Any client consumes the API over REST +
bearer JWT.

lexi-ai itself is vendored as an editable path dependency at `vendor/lexi-ai`
(gitignored symlink to `~/projects/lexi-ai`, or a copied source tree in
CI/deploy contexts) — see `pyproject.toml`'s `[tool.uv.sources]` in `apps/api`
and `apps/worker`.

## Two-Database Boundary

Pycil's Postgres owns exactly 9 tables (`apps/api/pycil/db/models.py` aggregates
every domain's SQLModel metadata for Alembic):

| Table | Domain | Purpose |
|---|---|---|
| `users` | auth | Account, role, ban state, token_version |
| `nodes` | hierarchy | Folder/Deck/Reference tree (adjacency list) |
| `folder_attributes` | hierarchy | Per-folder extra columns |
| `deck_attributes` | hierarchy | Per-deck extra columns (JSONB settings) |
| `user_nodes` | hierarchy | Per-user starred/pinned node state |
| `deck_senses` | content | Opaque `sense_id` membership in a deck |
| `user_sense_stats` | learning | FSRS memory state per (user, sense) |
| `review_log` | learning | Append-only first-attempt review history |
| `responses` | learning | Every graded answer (verdict persist-back) |

None of these hold dictionary content. lexi-ai owns `words`, `senses`,
`word_aliases`, `entry_links`, `questions`, `examples`, `collocations` in its
**own** database (`LEXI_DB_URL`) — a structural test
(`apps/api/tests/test_boundary.py`) asserts pycil's metadata never gains any of
these table names, and that `Lexicon(...)` is constructed nowhere except
`content/lexi_inprocess.py`.

Backup/restore must cover **both** databases to a consistent point — not yet
automated as of this migration (the `backup` compose service only backs up
pycil's Postgres).

## Ports & Adapters: the LexiClient Port

`apps/api/pycil/content/lexi_port.py` defines the `LexiClient` Protocol —
the only interface any pycil code is allowed to use to reach lexi-ai:

```python
class LexiClient(Protocol):
    async def search(self, query: str) -> list[SearchResult]: ...
    async def generate(self, source: SearchResult | str) -> Entry: ...
    async def get_senses(self, sense_ids: list[int]) -> list[SenseView]: ...
    async def generate_questions(self, entry: Entry, formats: list[str], n: int) -> list[Question]: ...
    async def grade(self, question: Question, answer: str) -> Score: ...
    async def get_question(self, question_id: int) -> Question | None: ...
```

`content/lexi_inprocess.py` is the only adapter and the only module allowed to
construct a `Lexicon`. `build_lexicon()` builds lexi-ai's own `Settings` from
pycil's config (`LEXI_DB_URL`, `LEXI_LLM_*`, `LEXI_CAMBRIDGE_DB_PATH`) and
`Lexicon.from_settings(...)` binds to lexi's DB. Question generation/grading/
lookup delegate to `lexicon.questions` (lexi-ai's `QuestionEngine`), not the
`Lexicon` object directly.

`lexicon.init()` (idempotent lexi-ai schema creation) runs once at API startup
(`main.py`'s `lifespan`) wrapped in a bare try/except — a missing Cambridge
SQLite file or unreachable lexi DB degrades search to empty results rather than
crashing API boot. The worker also runs `init()` on its own startup.

The API is **read/enqueue only** — it never calls `generate`/`generate_questions`
itself. All writes into lexi-ai's DB happen in the worker, which is the single
writer (avoids two processes racing lexi-ai's own dedup guards).

## Domains

### Auth (`pycil/auth/`)

Google OAuth 2.1 with PKCE, backend-issued bearer JWT. No server-side session
table — fully stateless.

- **`oauth.py`**: hardcoded Google endpoints (not a generic OIDC abstraction).
  Authorization-code flow only. PKCE verifier + state stored in Redis under a
  single-use key (`oauth:state:{state}`, 600s TTL) deleted immediately on
  exchange — replaying a `state` fails.
- **`tokens.py`**: the only module allowed to call `jwt.encode`/`jwt.decode`.
  Algorithm is pinned to `HS256` (`algorithms=["HS256"]`, never widened) and
  `sub`/`role`/`tv`/`exp`/`iat` are required claims — alg-confusion and
  `alg:none` forgeries are rejected. A future-dated `iat` (>30s clock skew) is
  rejected. Secret rotation: `jwt_secret_previous` is tried only if the current
  `jwt_secret` fails to verify (never applied to an already-expired signature).
- **`deps.py`**: `current_user` reads the JWT from the `Authorization: Bearer`
  header only (never a cookie — CSRF is out of scope by design). `role`,
  `token_version`, and `banned_at` are **re-read from the DB on every request**;
  JWT claims are edge-convenience only. A `token_version` mismatch (bumped on
  logout) or non-null `banned_at` rejects the request immediately, even
  mid-token-lifetime.
- **`router.py`**: `GET /auth/login` (returns the Google authorize URL),
  `GET /auth/callback` (exchanges code, upserts the user, returns a JWT),
  `POST /auth/refresh` (re-reads the DB user, reissues), `POST /auth/logout`
  (bumps `token_version`, revoking every previously issued token).

Any API client is expected to seal the returned JWT into its own session
mechanism (e.g. iron-session). No frontend lives in this repo; clients consume
the API over REST + bearer JWT.

### Content (`pycil/content/`)

Deck membership + word generation trigger. Never stores dictionary content.

- `POST /words` (202) — enqueues the `generate_word` worker job; returns
  immediately (async generation, no content in the response).
- `POST /decks/{node_id}/senses` (201) / `DELETE /decks/{node_id}/senses/{sense_id}`
  (204) — deck membership CRUD (`deck_senses` rows), owner-write-gated.
- `GET /decks/{node_id}/items` — resolves each sense's display content through
  the `LexiClient` port at read time (never from pycil's DB), owner-or-public
  read-gated.

### Hierarchy (`pycil/hierarchy/`)

Adjacency-list tree (`nodes.parent_node_id`) of FOLDER / DECK / REFERENCE nodes.

- **Tree and reference invariants.** Only FOLDER nodes accept children;
  locked service mutations reject self/descendant moves and cross-owner
  nesting. REFERENCE nodes point only at a live DECK that the actor owns or
  that is PUBLIC. The `0002_hierarchy_integrity` migration preflights these
  cross-row rules in existing data and adds the database-enforceable reference
  target-shape constraint.
- **Visibility.** Publishing a FOLDER requires explicit confirmation and grants
  inherited read visibility through same-owner descendants without rewriting
  their stored visibility. Writes remain owner-only. A reference always checks
  its target's current visibility and live ancestry, so a private or deleted
  target immediately contributes no content.
- **Subtree resolution** (`hierarchy/subtree.py`): a recursive CTE walks
  same-owner `parent_node_id` edges from a root down through descendants; DECK
  nodes contribute their id directly and REFERENCE leaves contribute only
  currently readable target decks. `resolve_sense_ids` then does a `DISTINCT
  sense_id` read over that deck-id set — entirely inside pycil's DB.
- **Stats** (`hierarchy/stats.py`) overlay that sense-id set against
  `user_sense_stats`: `folder_stats` (total/learned/mastered/avg_mastery, via
  PostgreSQL `ANY` array binds), `weakest_senses` (bottom-N by
  mastery), and `cefr_distribution` (buckets by CEFR level, resolved via the
  LexiClient port, never a cross-DB join).
- **Generation-safe L1 cache only.** `nodes.structural_generation` is bumped
  in the same transaction as membership, tree, visibility, and deletion edits
  for direct ancestors and reverse-reference consumers. Redis keys include the
  committed generation (and viewer where target visibility varies), so stale
  values are unreachable even if best-effort cleanup fails or a cache miss
  races a structural edit. No L2 cache.
- **IDOR gate** (`hierarchy/access.py`): every hierarchy/content/learning
  route that touches a node calls `require_node_access(session, node_id, user,
  write=...)`. `write=True` is owner-only (403 if not). `write=False` is
  owner-or-`PUBLIC` (else 404 — a private node's existence is never leaked to
  a non-owner). A missing or soft-deleted node is always 404. This is the
  single choke point closing what was previously a systemic IDOR gap.

Routes: `POST /nodes` (201), `PATCH /nodes/{node_id}/move`,
`PATCH /nodes/{node_id}/visibility`, `DELETE /nodes/{node_id}` (204), `GET /folders/{node_id}/stats`,
`GET /folders/{node_id}/weakest`, `GET /folders/{node_id}/cefr`.

### Learning (`pycil/learning/`)

Session queue, question-format routing, grading, and FSRS state updates.

**Session queue** (`session_queue.py::build_queue`): ranks in-scope senses by
retrievability (FSRS `recall()`), most-overdue first, mixing due reviews with
brand-new senses so the queue is never empty even when nothing is strictly
due yet.

**Question format routing** (`router_question.py::choose_format`): mastery
sets a difficulty *cap*, never a floor — a learner may get an easier format
than their mastery warrants but never harder, because a binary correct/wrong
grade can't distinguish "forgot the word" from "format was too hard," and
penalizing stability for the latter would be wrong. Three mastery bands map to
lexi-ai's four real format ids (`definition_mcq`, `contextual_mcq`, `cloze`,
`use_in_sentence`): low mastery is always `definition_mcq`; mid mastery mixes
`cloze` and `mcq`-family formats; high mastery opens up all four, weighted
toward `use_in_sentence`. The weighted pick is a deterministic SHA-256 hash of
`(sense_id, session_id)` — not `random` — so re-fetching "next" for the same
sense in the same session is stable, never re-rolled.

**Canonical session delivery** (`session_store.py`, `question_delivery.py`):
`POST /sessions` persists an ephemeral Redis queue and cursor. Next-question
delivery resolves the canonical question through `LexiClient`, omits answer
material from the client payload, and records the issued question/sense binding.
`POST /answers` validates that binding before accepting an answer.

**Answer flow** (`service.py::answer`, called from `POST /answers`):

1. The client sends only `question_id` + raw answer — **never** a question
   payload. The server re-fetches the authoritative `Question` via
   `client.get_question(question_id)` and grades that, closing an
   answer-key-tamper vector.
2. `client.grade(question, answer)` returns lexi-ai's `Score` (rule-based for
   `mcq`/`cloze`, LLM-judge for `use_in_sentence`). `grading.py::fsrs_grade`
   maps `Score.correct` to the FSRS binary grade (`GRADE_GOOD=3` /
   `GRADE_AGAIN=1`) — pycil does no grading logic of its own.
3. A per-`(user_id, sense_id)` row lock serializes concurrent updates to the
   same sense.
4. Only the **first attempt per sense per session** (claimed by the durable
   `session_sense_attempts` uniqueness constraint) mutates FSRS state and
   appends a `review_log` row. Repeat attempts in the same session still grade
   and persist a `responses` row, but don't move stability/mastery again.
5. `responses` always gets a row — this is the recoverable verdict
   persist-back: if the realtime push is missed, the client can refetch.

**Durable async verdicts** (`service.py::apply_verdict`, used by the worker's
`grade_answer_v1` job for LLM-judged `use_in_sentence` answers): the pending
response retains raw input only until grading completes. A fenced, expiring
lease prevents two workers from applying one verdict; already terminal rows
are no-ops. `reconcile_pending_grades` scans bounded, unleased rows for lost
enqueues or expired leases and requeues them; after 24 hours it records a
terminal `expired` response and clears the raw input.
Clients receive a `responseId` immediately and can poll `GET /responses/{id}`.

FSRS math lives in `packages/shared-py/shared/fsrs/` (see below);
`learning/fsrs_wrapper.py` is a thin domain-shaped wrapper (`elapsed_days`,
`first_review`, `next_state`) — no new math there.

Routes: `POST /sessions` (builds + caches the queue in Redis under
`session:{id}`, 8h TTL), `GET /sessions/{id}/next`, `POST /answers`,
`GET /responses/{id}`.

### Folder analytics

Folder reads resolve the owner's live hierarchy definition set. `GET
/folders/{id}/items` paginates lexical views, `GET /folders/{id}/history`
returns stable daily buckets with review counts and a carry-forward average
mastery series, and `GET /me/stats` returns the caller's global learning
totals. History validates a bounded date window and uses the `0004` review-log
index. Its large-set bind path uses PostgreSQL `ANY` arrays. The opt-in
2k/100k benchmark is recorded in the hardening plan reports.

### Realtime (`pycil/realtime/` + worker's `pycil_worker/realtime.py`)

Centrifugo v5 for push updates (grading verdicts, job status). Channels are
strictly owner-scoped (`shared/realtime/channels.py`):

```
users:{uid}#{uid}                          — general per-user channel
users:{uid}:jobs:{job_id}#{uid}             — word-generation job status
users:{uid}:grading:{response_id}#{uid}     — answer grading verdict
```

`job_id`/`response_id` are enumerable. `centrifugo-config.json` enables
Centrifugo's native user-limited channels for the `users` namespace. The
terminal `#{uid}` is checked by Centrifugo against the authenticated connection
subject, so user A cannot subscribe to user B's channel even with an otherwise
valid token. The connection token (`GET /realtime/token`) is signed with
`CENTRIFUGO_TOKEN_HMAC_SECRET` — separate from the API's `JWT_SECRET`.

Publishing (`realtime/client.py::publish`) is **best-effort**: an
`httpx.HTTPError` is swallowed, never failing the caller. This is safe because
every event that gets published also has a durable source of truth already
committed (`responses` row for grading, job state for word generation) — a
missed push is recoverable on next fetch, not a lost write.

### Worker (`apps/worker/pycil_worker/`)

arq worker, four jobs registered in `WorkerSettings.functions`
(`main.py`), `max_tries=2`:

| Job | Purpose |
|---|---|
| `generate_word` | Lazy dictionary generation: search lexi-ai, or generate from the raw query string if search misses. Publishes job status over Centrifugo. Writes only to lexi-ai's DB — pycil stores nothing from this job except the deck-membership row a later `add_sense` call creates. |
| `generate_question` | Delegates to `client.generate_questions(entry, formats, n)`. |
| `grade_answer_v1` | Resolves a pending async (LLM-judged) verdict via `service.apply_verdict`; idempotent — returns `{"status": "duplicate"}` if already graded; publishes the grading result on success. The worker also retains legacy `grade_answer` while its backlog drains. |
| `reconcile_pending_grades` | Cron sweep every ten minutes for durable pending responses whose enqueue was lost or lease expired; stale raw answers are purged. |

`on_startup` builds the shared `InProcessLexiClient`, runs `lexicon.init()`
once, and opens the DB engine/session factory; `on_shutdown` disposes the
engine. The worker reuses the API's own package (a path dependency in
`apps/worker/pyproject.toml`) for the `LexiClient` port, `learning.service`,
and models — so grading/FSRS logic is not duplicated.

`apps/api/pycil/worker_bridge/` exists in the api package but is currently an
**empty, unmounted module** — not wired into `main.py`'s router mounts and not
referenced anywhere else in the codebase. Treat it as a placeholder, not part
of the live worker-invocation path (jobs are enqueued directly via the arq
Redis pool in `content/service.py::request_word`, not through this package).

`apps/worker/tests/test_worker_registration.py` asserts that the reconciler
and its cron registration remain part of the worker settings.

## FSRS-4.5 Engine (`packages/shared-py/shared/fsrs/`)

A verbatim port of the published `fsrs4anki` v4.5 defaults — no per-user
weight fitting. The engine only ever sees a binary grade:
`GRADE_GOOD = 3` (correct) or `GRADE_AGAIN = 1` (wrong); `Hard(2)`/`Easy(4)`
are never emitted, so a few weights from the published 17-weight table are
unused dead constants (kept for fidelity to the source table).

- **Retrievability**: `R(t) = (1 + (19/81)·t/S)^-0.5` — a power-law forgetting
  curve where `R = 0.9` exactly when elapsed time `t` equals stability `S`.
- **Mastery**: `mastery = round(100·S/(S+30))` — a saturating, monotonic 0-100
  display value derived from stability (not retrievability, which oscillates
  hourly and is unstable to show).
- **Initial state**: seeded from the grade on first review; difficulty is
  clamped to `[1, 10]`.
- **Update on success**: stability grows, scaled by current difficulty and
  retrievability at review time (lower retrievability on a correct answer
  yields a bigger stability jump — the "desirable difficulty" effect).
- **Update on failure**: stability shrinks, bounded by a function of
  difficulty and pre-lapse stability.
- **Difficulty update**: a linear delta mean-reverted toward the "Good"
  target difficulty, clamped to `[1, 10]` — standard FSRS "ease hell"
  prevention.
- **Interval** is `clamp(stability, 30min, 365days)`.

All weights are hardcoded (see `packages/shared-py/shared/fsrs/weights.py`)
and never fit per-user.

## Deployment

### Migration gate

`docker-compose.yml`'s `migrate` service runs `alembic upgrade head` once
(idempotent — a no-op if already at head) and must complete successfully
(`condition: service_completed_successfully`) before `api` or `worker` start.
A healthy Postgres container is not the same as a migrated one; this gate
makes that explicit rather than relying on app-level retry.

### Images

`apps/api/Dockerfile` and `apps/worker/Dockerfile` both build from the repo
root (build context = `.`, not the app subdirectory) because they need to
`pip install -e` local path packages: `packages/shared-py`, `vendor/lexi-ai`,
and `apps/api` (the worker additionally installs `apps/worker` itself, on top
of `apps/api`). Both drop root to a non-privileged `appuser` after install.

### Environment

See `.env.example`. Sections relevant to this stack: Postgres, Redis, lexi-ai
(`LEXI_DB_URL`, `LEXI_LLM_*`, `LEXI_CAMBRIDGE_DB_PATH`/`LEXI_CAMBRIDGE_HOST_PATH`),
Centrifugo (`CENTRIFUGO_URL`, `CENTRIFUGO_API_KEY`, `CENTRIFUGO_TOKEN_HMAC_SECRET`).
The Cambridge SQLite source (~142MB) is not committed — copy it from
`~/projects/lexi-ai/data` before first `docker compose up` or `search()` will
return empty results.

`.env.example` was scrubbed to backend-only variables when the frontend
(`apps/web`) was removed from this repo — the older `# --- Auth.js v5 (web) ---`
block (`AUTH_SECRET`, `OIDC_*`, Dex-provider docs) is gone. Everything left is
consumed by `apps/api`/`apps/worker` or `docker-compose.yml`.

## Known Gaps

These are real, unresolved gaps as of this migration — noted here rather than
silently omitted, so they aren't mistaken for finished work:

- **Hardening work is in progress.** Phase 1 established a reproducible API
  test baseline: local runs provision disposable PostgreSQL through
  Testcontainers, while CI supplies `TEST_DB_URL`. Phase 2 closes the eight
  hierarchy/cache contract cases. Later phases introduced canonical session
  delivery, durable grading, and analytics routes; Phase 5 and Phase 6 remain
  in progress and are not completion guarantees. See the
  [hardening plan](../plans/260716-1321-system-design-alignment-hardening/plan.md)
  and its [baseline report](../plans/260716-1321-system-design-alignment-hardening/reports/current-test-baseline.md).

- **CI/CD repointed at the new stack.** `.github/workflows/{test,deploy,nightly}.yml`,
  `scripts/deploy.sh`, and the root `Makefile` now target `apps/api`/`apps/worker`/
  `packages/shared-py` and the `api`/`worker`/`migrate` compose services (not the
  old `pycil-core` name). The Caddy-validate CI gate and the two root Caddyfiles
  were removed (Caddy was already dropped from `docker-compose.yml` in Phase 1).
  `docker-compose.staging.yml`, `scripts/staging-up.sh`, `scripts/mc-mkbucket.sh`,
  and `infra/dex/` were removed outright rather than patched — they wired the old
  `pycil-core`/Dex OIDC/MinIO local-dev stack, none of which has an equivalent in
  the new backend (Google-only OAuth, no S3/media). The frontend (`apps/web`) and
  its Playwright e2e suite were removed with it — `.github/workflows/test.yml` has
  no `e2e` job (there's nothing left to run). **Still open:** re-introducing
  browser e2e coverage would need a new auth-testing strategy (mock Google, or
  mint a JWT directly) plus specs written against FSRS/mastery — and a client to
  drive, which no longer lives in this repo.
- **This repo is backend-only.** The Next.js frontend (`apps/web`) has been
  removed; any client consumes `apps/api` over REST + bearer JWT and subscribes
  to Centrifugo directly. There is no in-repo UI, auth-cookie sealing, or
  Centrifugo-JS integration to maintain here.
- **Worker behaviour coverage remains sparse.** The registration test covers
  the pending-grade reconciler and cron, but job-level integration coverage is
  still needed.
- **Live Centrifugo ACL check is opt-in.**
  `RUN_CENTRIFUGO_LIVE=1 uv run pytest tests/realtime/test_live_centrifugo_acl.py`
  starts a temporary v5 broker and proves a user A connection is denied user
  B's native `#userB` channel. It is excluded from the default hermetic suite
  because it needs Docker.
- **`apps/pycil-core`** (the pre-migration Python/FastAPI/SQLModel backend) is
  intentionally kept on disk as a historical reference per the migration
  plan, not deleted. It is not part of the running stack and CI no longer
  builds, tests, or deploys it.

## Historical / Superseded Design Docs

`docs/designs/fsrs-learning-engine.md` and
`docs/designs/vocabulary-hierarchy-stats-architecture.md` are the original
design proposals this migration implemented. They're kept for the detailed
rationale behind FSRS parameter choices and the hierarchy/stats data model,
but treat this file as authoritative for what's actually implemented — the
design docs predate some implementation decisions (e.g., exact route shapes,
cache-busting strategy details).

## See Also

- [codebase-summary.md](./codebase-summary.md) — file-level map.
- [project-roadmap.md](./project-roadmap.md) — phase status.
- [project-changelog.md](./project-changelog.md) — dated change history.
- `plans/260705-0032-python-greenfield-migration/plan.md` — the migration plan,
  including its red-team review and validation log.
