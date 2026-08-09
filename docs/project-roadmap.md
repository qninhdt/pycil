# Pycil — Roadmap

**Current status:** backend rebuilt as a Python greenfield migration
(FastAPI + SQLModel + Alembic) with `lexi-ai` embedded as a domain library, and
a tracked Next.js 16 web app (`apps/web`) rebuilt against the completed contract.
The current source of truth is
[`current-system-architecture.md`](./current-system-architecture.md),
[`codebase-summary.md`](./codebase-summary.md), and the
[`frontend-integration-guide.md`](./frontend-integration-guide.md).

The original 7-day sprint plan and its v0.2/v0.3 follow-ups (further down this
file) describe the pre-migration Python/Next.js MVP. They're kept for
history; they do not describe the current system.

---

## Python Greenfield Migration (historical plan)

**Plan:** `plans/260705-0032-python-greenfield-migration/plan.md`
The original plan called for a separately deployed `lexi-ai` authority and an
external Next.js BFF. The implementation now embeds `lexi-ai` and ships the BFF
in `apps/web`; the completed current architecture is documented above.

| Phase | Name | Status |
|---|---|---|
| 1 | Scaffold & Infrastructure | Complete |
| 2 | Baseline Schema & Migration | Complete |
| 3 | Auth Domain | Complete |
| 4 | FSRS Engine | Complete |
| 5 | Content & Lexi-AI | Complete |
| 6 | Learning Domain | Complete |
| 7 | Hierarchy & Stats | Complete |
| 8 | Realtime Centrifugo | Complete |
| 9 | Worker Redesign | Complete |
| 10 | Frontend Auth & Rename | Superseded by the in-repo web rebuild |
| 11 | Integration Wiring | Complete |
| 12 | Tests & Docs | Complete |

## Assistant Agent MVP (active)

**Plan:** `plans/260716-1729-assistant-agent-system/plan.md`

| Phase | Name | Status |
|---|---|---|
| 1 | Provider, dependencies, and privacy configuration | Complete |
| 2 | Owner-bound persistence, facades, and migration | Complete |
| 3 | Bounded LangChain graph and tools | Complete |
| 4 | Owner-scoped SSE run recovery | Complete |
| 5 | Durable HITL, audit, expiry, and deletion | Complete |
| 6 | Security and integration tests | Complete |

**Rollout:** the API and worker implementation is present, with no feature
flag. It activates only when `ASSISTANT_API_KEY` and `ASSISTANT_BASE_URL` are
configured for a dedicated OpenAI-compatible provider (not OpenRouter).
Sensitive mutations ship with the MVP behind durable per-action human approval;
verification is complete: API 122 passed / 2 skipped; worker 3 passed. The
provider protocol smoke test runs against a local OpenAI-compatible server.

**Phase 10 detail:** the original frontend (`apps/web`, Next.js 15) was removed
from this repo during the greenfield migration. It was later rebuilt from
scratch against the completed contract — see the Web Frontend Rebuild milestone
below.

## Web Frontend Rebuild (complete; live-stack verification deferred)

**Plan:** [Web Frontend Rebuild](../plans/260727-1332-web-frontend-rebuild/plan.md)

A fresh `apps/web` (Next.js 16 App Router, React 19, Tailwind v4, TanStack
Query) rebuilt on the retained BFF seam: bearer tokens stay server-side in an
encrypted `iron-session` cookie, and every screen consumes `/v1` through server
actions. The rebuild also closed backend contract gaps the frontend needed
(`GET /v1/senses/{id}`, `GET /v1/sessions/{id}`, node `path`, deck `itemCount`,
per-item learning state, enriched weakest, the corrected deck-settings pair,
`/v1/me/{history,cefr,weakest}`) and fixed three backend defects surfaced along
the way — a no-op deck-settings endpoint, `restore_delivered` wedging a sense
after an aborted answer, and a `RunEventRead` serialization mismatch.

Phases 1–12 shipped. Phase 13 (verification) completed its stack-independent slice:
the Vitest unit layer (session reducer, error taxonomy, snapshot reconciliation,
mastery mapping, the assistant transport), a runnable ten-check design-system
audit, Storybook stories for the feature components, and a CI web job. The
remaining phase-13 deployment checks (Playwright E2E against `docker compose`,
the generation tier, a11y runs, and the screenshot set) need a live stack and are
deferred to a nightly workflow. Phase 14 is this docs sync.

### Cut P1 scope (recorded as decisions, not omissions)

These were in the design's ambition and deliberately left out of the rebuild;
re-discovering them later as "missing" would be wrong — they were cut on purpose:

- TTS / audio pronunciation (the product ships IPA as text only).
- Streaks and the activity heatmap.
- The sense relation graph as a visual (relations ship as a grouped list).
- User themes and tags.

### Deliberate capability cuts made during red team

- Folder `dueCount` and folder aggregates were removed from the node **list**
  response and are served on the opened node instead: they cannot be aggregated
  in bounded time across a listing.
- The `search_words` per-result `get_entry` N+1 was left in place rather than
  amplified; the search path stays single-scoped.

### Backend follow-up (known, not yet fixed)

A run left `RUNNING` after a mid-stream client disconnect is never marked
abandoned server-side: `GeneratorExit` is a `BaseException` and escapes
`stream_run`'s `except Exception` handlers, so no terminal event is ever
written. The frontend copes honestly — it re-reads persisted events and offers a
resend rather than claiming the reply will resume — but an interrupted reply can
only be resent, not resumed, until the server reaps such runs.

## System Design Alignment and Hardening (complete)

**Plan:** [System Design Alignment and Hardening](../plans/260716-1321-system-design-alignment-hardening/plan.md)

| Phase | Name | Status | Outcome |
|---|---|---|---|
| 1 | Canonicalize Contracts and Baseline | Complete | Current Python/FSRS/public-plus-isolated-Lexi-schema design contracts recorded; local API tests provision disposable PostgreSQL with Testcontainers, CI retains `TEST_DB_URL`, and 19 known gaps are strict xfails for later phases. |
| 2 | Hierarchy and cache integrity | Complete | Additive `0002` migration preflights invalid legacy hierarchy data; service rules enforce tree/reference/membership invariants, inherited public-folder reads, live-reference revocation, and DB-generation cache invalidation. |
| 3 | Canonical session delivery | Complete | Redis session queue/cursor and issued-question binding deliver canonical, answer-sanitised questions; first attempts are recorded durably. |
| 4 | Grading persistence and concurrency | Complete | Pending `use_in_sentence` responses use fenced leases, polling, and worker reconciliation. |
| 5 | Statistics contract and scale | Complete | Folder items/history and global stats routes use the canonical learned-sense relation. |
| 6 | Deployment integration and realtime ACL | Complete | Additive migrations `0002`–`0007`, Centrifugo native user-limited channel ACL, runtime/config validation, versioned grading jobs with legacy drain, and worker behavior coverage are present. |

The Phase 1 baseline recorded 13 shared-package tests passing and 64 API tests
passing with 19 expected strict xfails. Phase 2 resolves the eight
hierarchy/cache contract cases; later hardening work promotes the canonical
session, grading, and statistics contracts into implementation while the active
phases above retain their stated validation work. See the
[baseline report](../plans/260716-1321-system-design-alignment-hardening/reports/current-test-baseline.md).

**Operational gaps not tracked by any phase above** (found during the Phase
12 docs pass; CI/deploy.sh/Makefile closed 2026-07-06, rest still open):

- CI targets `apps/api`, `apps/worker`, and `packages/shared-py`; it also
  validates the Compose render, migration head, API/worker image builds, and
  Caddy configuration.
- ~~`apps/pycil-core`, `docker-compose.staging.yml`/Dex/MinIO, and
  `apps/web/e2e`~~ — removed 2026-07-06 (superseded/unreferenced by the new
  stack; see system-architecture.md § Known Gaps for what each depended on).
- Browser e2e coverage is scaffolded but not yet running in CI. `apps/web` now
  has a Vitest unit layer and a CI web job (typecheck, lint, unit, design-system
  audit, build, Storybook build); the Playwright journey suite — OAuth via the
  `dev_identity` CLI seam, sealed-session validation, the study loop, and SSE
  settlement — needs a live `docker compose` stack and is deferred to a nightly
  workflow (Web Frontend Rebuild, phase 13).
- The remaining deployment gate is a real two-Compose smoke test with a
  published Cambridge artifact; it cannot be hermetic because it validates
  the runtime artifact download and shared Docker network.
- 2k/100k statistics and live Centrifugo ACL checks are opt-in Docker-backed
  tests; they are excluded from the default suite to keep it hermetic. The local
  benchmark baseline is recorded in the active plan's query-budget report; the
  default suite covers the SQL/proxy authorization contracts without requiring a
  live broker.
- Backups must cover both Pycil's `public` schema and embedded Lexi's isolated
  `lexi` schema in the shared PostgreSQL database.

---

## Historical: Pre-Migration Sprint Roadmap (superseded)

The rest of this document is the original MVP sprint plan and its v0.2/v0.3
follow-ups. It describes the pre-migration stack (Go-free but pre-lexi-ai,
single Postgres, Auth.js, ELO, SSE) and is kept for history only.

**Sprint window:** 2026-05-25 → 2026-05-31 (Day 1 → Day 7)
**Target:** Public launch on Day 7
**Plan source:** `plans/idea.md`, `plans/260525-0124-pycil-mvp-implementation/plan.md`

---

## v1 Phase Status (post-sprint)

| Day | Phase | Status | One-line outcome |
|-----|-------|--------|------------------|
| 1 | Foundation & Infra | Completed | docker-compose stack live; Caddy + auth + Alembic 0001_init shipped |
| 2 | Content CRUD | Completed | Folder/deck/term CRUD + dashboard + breadcrumb wired through pycil-core |
| 3 | AI Term Pipeline | Completed | `generate_term` job + term-keyed SSE + per-user `user_term_jobs` ownership + spend cap |
| 4 | Question Generation | Completed | MCQ-only via shared `BaseQuestion` ABC; Write/Fill plug-points kept abstract |
| 5 | Learning Mode & ELO | Completed | `pycil_core/learning/` ELO module + Redis-backed session state + 11-level mastery |
| 6 | Polish & Launch Prep | Completed | Landing, onboarding seed, rate limit, error boundaries, mobile pass |
| 7 | Launch | Completed (docs ready; live launch event pending) | Smoke + assets + Show HN/PH copy in `docs/launch-copy/` |

Plan source of truth: `plans/260525-0124-pycil-mvp-implementation/plan.md` and per-phase files.

---

## Day 1 — Foundation & Auth

**Deliverables**
- VPS provisioned (Hetzner CCX13 or DO 2vCPU/4GB)
- Caddy reverse proxy with auto-TLS (Let's Encrypt)
- `docker-compose.yml` with: web, pycil-core, worker, postgres, redis, caddy
- GitHub Actions deploy pipeline (SSH + `docker compose pull && up -d`)
- Postgres schema migrated (Alembic init + v1 tables)
- Auth.js v5 in Next.js with Google OAuth → working sign-in flow
- Domain pointing at VPS, HTTPS green

**Acceptance**
- Visit https://<domain>/, click "Sign in with Google", land on protected `/dashboard`
- `docker compose ps` shows all services healthy on VPS

**Risk:** Low. Standard infra setup.

---

## Day 2 — Content CRUD

**Deliverables**
- `pycil-core` FastAPI scaffolding with SQLModel + Alembic
- Endpoints: `POST/GET/PATCH/DELETE /api/nodes` (folders + decks)
- Endpoint: `POST /api/decks/:id/terms` (manual term entry, no AI yet)
- Dashboard UI: list root nodes, create folder/deck, breadcrumb nav
- Deck detail UI: list terms, add-term input
- Auth.js session validation in FastAPI (read shared `sessions` table)

**Acceptance**
- User signs in, creates folder "English", creates deck "B2 verbs", adds term "resilience" (no enrichment yet)
- Refresh page → data persists
- Other user's session cannot read your decks

**Risk:** Low. CRUD + UI work.

---

## Day 3 — AI Pipeline

**Deliverables**
- `worker` service scaffolded (arq + LangChain + httpx OpenRouter)
- `LLMClient` interface (abstraction over LangChain — swap-ready)
- `prompts/` directory with Jinja2 templates: `generate_term.md`, `role.md`
- `generate_term` job: input term value → call LLM → parse JSON → INSERT definitions + paraphrases + example_sentences
- `jobs` table + `pycil-core` job-enqueue logic + Redis lock for idempotency
- SSE endpoint `/api/jobs/:id/stream` in Next.js
- Frontend: add-term flow shows live "Generating…" → enriched view via SSE

**Acceptance**
- Add term "ephemeral" → within 30s, definition + 3 paraphrases (A2/B1/C1) + 3 examples appear in UI without refresh
- Submitting same term twice within 5min only triggers one LLM call (Redis lock works)

**Risk:** **Medium.** SSE plumbing + Redis Pub/Sub + LLM JSON parsing all new.

---

## Day 4 — Question Generation

**Deliverables**
- Prompts: `mcq.md`, `fill_in_blank.md`, `write.md` (extending `role.md`)
- `generate_question` job: input definition_id + type → LLM → INSERT into `questions` table
- `BaseQuestion` abstraction (per idea.md §4.6) with `generate()` + `check_answer()` per type
- Question fetch API: `GET /api/definitions/:id/question?type=...&difficulty=...`
- Question rendering UI components (MCQ, Write, Fill) — Shadcn forms + Zod

**Acceptance**
- For any enriched term, generate one MCQ + one Write + one Fill question, render correctly, validate answers
- Same definition + type = cached question reused (no duplicate LLM call)

**Risk:** Medium. Multiple question types, polymorphic rendering.

---

## Day 5 — Learning Mode + ELO (HIGH RISK)

**Deliverables**
- Term selection algorithm (due → new → upcoming) per idea.md §4.2
- Learning session API: `POST /api/decks/:id/learn`, `GET /sessions/:id/question`, `POST /sessions/:id/answer`
- Redis-backed session state (`learning_session:{id}`)
- Round logic (P=5 terms per round, repeat incorrect, Q correct first answers = reviewed)
- ELO scoring implementation (R, E, Δ, T, I formulas from idea.md §4.3)
- Next-review interval snapping (predefined list)
- 11 mastery levels with explicit ELO→level mapping
- Learning UI: question card, progress bar, round summary, session summary

**Acceptance**
- Start session with 10 terms → answer correctly + incorrectly → ELO updates → `next_review_date` written → mastery level recomputed
- Synthetic test: 100 sessions on same user → ELO trajectories look reasonable (no runaway, no division by zero)

**Risk:** **HIGH.** Most complex day. ELO math + UI compression.

**Mitigation**
- Day 4 evening: prototype ELO calc in isolation (unit-testable Python module, no UI)
- Day 5 morning: wire to API
- Day 5 afternoon: UI

---

## Day 6 — Polish & Launch Prep

**Deliverables**
- Landing page (`/`) — value prop, screenshot, "Sign in" CTA
- Onboarding: empty-state UX for new users (sample folder + deck on first sign-in)
- Error boundaries on all pages
- Rate limiting on `pycil-core` (5 LLM gens/min/user, simple Redis counter)
- Loading skeletons, Toast notifications
- Mobile-responsive review (Tailwind audit)
- Privacy + Terms stubs (legal-thin)
- README with screenshots + tech stack + setup

**Acceptance**
- Cold-load landing page < 2s
- Mobile usable for sign-in + add term + study
- README clear enough that AI agent could re-deploy from scratch

**Risk:** Low. Polish work.

---

## Day 7 — Launch

**Deliverables**
- Production smoke test (full user journey: sign up → create deck → add 10 terms → study → review)
- Show HN post drafted
- Product Hunt asset prep (logo, screenshots, GIF)
- Hotfix capacity (Day 7 afternoon kept clear)
- Submit to Show HN
- Monitor logs + respond to user feedback in real-time

**Acceptance**
- Live URL stable for 4+ hours under launch traffic
- Zero P0 bugs reported in first hour
- At least 1 external user completes a learning session

**Risk:** Medium. Launch-day surprises.

---

## Critical Path & Buffer

```
Day 1 ──> Day 2 ──> Day 3 ──> Day 4 ──> Day 5 ──> Day 6 ──> Day 7
 LOW       LOW       MED       MED      HIGH      LOW       MED
```

**No buffer days.** Day 7 afternoon is the only slack.

**If Day 5 slips:** cut MCQ-only learning (drop Write + Fill from learn mode, keep them as standalone exercises). ELO is non-negotiable per user direction.

**If Day 3 slips:** cut SSE, fall back to client polling `/api/jobs/:id` every 2s. Functional, less elegant.

---

## Daily Ritual

- **Morning (15min):** review yesterday's notes, set Day-N task list in `TaskCreate`
- **Evening (30min):** commit + deploy + smoke test on prod, write 3-bullet daily journal
- **Each task:** TDD where ELO/scoring is concerned; otherwise smoke-test by hand (no formal tests in sprint)

---

## v0.2 Priorities (cooked 2026-05-26 — `plans/260525-1446-pycil-v02-feature-fill/`)

Top-of-stack from the retro template — all five shipped as scaffolds + critical paths:

1. **Backups** ✓ — `infra/backup/{Dockerfile,backup.sh,restore.sh}`; nightly `pg_dump | restic` to B2 with 7d/4w/6m retention.
2. **Sentry** ✓ — `sentry_sdk.init` in pycil-core lifespan; envs in config.
3. **Write + Fill question types** ✓ — `WriteQuestion` + `FillInBlankQuestion` ABCs; tier-ladder grading; FE renderers.
4. **i18n** ✓ — `messages/{en,vi}.json`; BE error codes via snake_case strings.
5. **Formal test suite retrofit** ◐ — `pytest` conftest + grading + gamification + question + migration tests; Playwright E2E deferred to v0.3.

## v0.2 Out-of-Sprint (pulled in per user override, cooked 2026-05-26)

- ✓ Topic + usage tags (`definitions.tags`)
- ✓ Public/cloned decks (`/explore`, `clone_service.deep_clone`)
- ✓ Translation pipeline (`translate_definition` arq job + JSONB cache)
- ✓ TTS via Gemini Flash (B2 upload, 7d signed URL)
- ✓ SHORTCUT node type (`nodes.target_node_id`)
- ✓ Mobile PWA (next-pwa, manifest, online-only)
- ◐ Payments/premium tier — Stripe webhook + idempotency real; checkout UI deferred (locked v0.3)
- ✓ Question diversification (`questions.variant_seed`)
- ✓ Per-question ELO calibration (`questions.elo` column + `calibrate_question_elo` cron seam)

## v0.3 backlog (deferred from v0.2 cook)

- PWA icon assets (192/512/maskable.png, og-image.png)
- Stripe checkout UI + ENFORCE_TIERS flip
- ✓ Playwright E2E suite (auth-flow, create-deck-and-term, learn-session, flashcard-mode, explore-page, sign-out-everywhere)
- `last_llm_response` retry idempotency wired into worker code paths
- OpenRouter model fallback chain implementation
- Caddy `@sse` matcher widened to `/chat/sessions/*/stream`
- LLM-as-judge tier-4 grading (currently disabled via `use_llm_fallback=False` default)
