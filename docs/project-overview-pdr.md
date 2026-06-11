# Pycil — Project Overview PDR

**Status:** Draft v1 (post-brainstorm 2026-05-25)
**Owner:** Solo dev + Opus 4.7 coding agent
**Sprint:** 7-day public-launch sprint
**Long-form vision:** see `plans/idea.md`

---

## 1. Product Vision

Pycil is an AI-powered vocabulary learning app — a Quizlet/Anki successor where every term is enriched on-demand by an LLM (definitions, paraphrases per CEFR level, example sentences, synonyms/antonyms) and reviewed via an ELO-driven spaced-repetition engine.

**Differentiators vs. existing tools**:
- LLM-generated content per CEFR level — no manual card authoring
- ELO mastery scoring (continuous), not interval-doubling SM-2
- Hierarchical content (folders + decks)
- Multiple question types (MCQ, Write, Fill-in-blank) auto-generated per term

## 2. Scope

### v1 (1-week launch)
- Google sign-in (Auth.js)
- Hierarchical folders + decks (private only)
- Manual term entry → AI background job → enriched data
- Multiple-choice / Write / Fill-in-blank questions
- Learning sessions with ELO scoring + next-review scheduling
- 11 mastery levels (per `idea.md`)
- Docker Compose deploy on single VPS
- Single-language UI (English)

### Shipped beyond the original v1 cut (reconciled 2026-06-11, rehab)
These were listed out-of-scope in the original plan but DO ship and are kept:
- Public/cloned decks
- TTS pipeline (server-rendered audio via worker + S3)
- Translation pipeline
- Sentry error reporting + OpenTelemetry tracing (opt-in, no-op when unconfigured;
  see `codebase-summary.md` → Observability). Loki/Tempo/Grafana still deferred.

### Explicitly out of v1 (genuinely not built / removed in rehab)
- `SHORTCUT` node type
- Topic/usage tags on definitions
- i18n (next-intl)
- Payments / premium tier
- Mobile native app
- Loki / Tempo / Grafana log+metrics stack (tracing/Sentry DO ship; see above)
- Backups: shipped as an opt-in restic compose profile, not a deferred item

## 3. Architecture

Three services, single repo, single docker-compose:

```
[Browser]
   ├─ HTTPS ──> Caddy (TLS, reverse proxy)
                 ├─> web         (Next.js 15, port 3000)
                 │     ├─ UI + Auth.js (Google OAuth)
                 │     ├─ SSE endpoint /api/jobs/:id/stream
                 │     └─ HTTP ──> pycil-core
                 ├─> pycil-core  (FastAPI, port 8000)
                 │     ├─ CRUD: nodes, decks, terms, learning sessions
                 │     ├─ ELO scoring, next-review scheduling
                 │     └─ Enqueues jobs ──> Redis (arq queue)
                 ├─> worker      (Python arq consumer)
                 │     ├─ generate_term, generate_question jobs
                 │     ├─ LangChain ──> OpenRouter ──> LLMs
                 │     ├─ Writes results to Postgres
                 │     └─ Publishes ──> Redis Pub/Sub (results:{job_id})
                 ├─> Postgres 16 (single DB, all tables)
                 └─> Redis 7    (queue + Pub/Sub + cache + session state)
```

### Why this split (not monolith, not 8-services)

| Boundary | Reason |
|---|---|
| `web` separate from `pycil-core` | Auth.js works best in Next.js. FastAPI focuses on domain logic. Clean FE/BE split. |
| `pycil-core` separate from `worker` | LLM calls are slow (5-30s), block API workers, scale differently. Async queue is mandatory. |
| Single Postgres, single Redis | No data-isolation requirement. Cross-service queries need joins (e.g., learning service + content service in idea.md). Premature split. |

### Inter-service communication

- `web` → `pycil-core`: HTTP/JSON. Auth via shared Postgres `sessions` table (Auth.js writes, FastAPI reads).
- `pycil-core` → `worker`: enqueue via arq (Redis list).
- `worker` → `web` (real-time updates): publish to Redis Pub/Sub channel `results:{job_id}`. `web` SSE endpoint subscribes and forwards to client.

## 4. Tech Stack

### Frontend (`web`)
- Next.js 15 (App Router), React 19, TypeScript
- Auth.js v5 with Google provider + Postgres adapter (`@auth/pg-adapter`)
- Shadcn UI + Tailwind CSS
- TanStack Query for client state
- react-hook-form + Zod for forms
- EventSource API for SSE consumption

### Backend (`pycil-core`)
- Python 3.12, FastAPI
- SQLModel (Pydantic + SQLAlchemy) + Alembic migrations
- asyncpg driver
- Pydantic Settings for config

### Worker (`worker`)
- Python 3.12 (shared venv with `pycil-core`)
- arq (async Redis queue)
- LangChain (LLM orchestration) — **isolated behind `LLMClient` interface to allow swap**
- Jinja2 for prompt templating in `prompts/*.md` (vanilla `{% include %}` only — no custom directives)
- httpx for OpenRouter HTTP

### Infra
- Postgres 16, Redis 7, Caddy 2 (auto-TLS via Let's Encrypt)
- Single VPS (Hetzner CCX13 or DO 2vCPU/4GB ≈ $20/mo)
- docker-compose orchestration
- GitHub Actions: lint + test + SSH deploy (`docker compose pull && up -d`)

## 5. Data Model (v1 schema)

Cuts from `idea.md`:

| Cut | Replacement |
|---|---|
| `SHORTCUT` node type + `shortcut_attributes` | None (drop) |
| `PUBLIC` visibility | All decks `PRIVATE` (visibility column kept for v0.2) |
| `definition_ids[]` array on nodes | `deck_definitions(deck_id, definition_id, position)` junction |
| `path` JSON denormalization | `parent_id` + recursive CTE for breadcrumbs |
| `topic_tags`, `usage_tags` enums | Defer to v0.2 |
| `text_audio_files`, `text_translations` | Drop from v1 |
| Firestore for job status | `jobs` table in Postgres + Redis Pub/Sub |

Kept from `idea.md`:
- `users`, `nodes` (FOLDER/DECK only), `folder_attributes`, `deck_attributes`
- `terms`, `definitions`, `definition_paraphrases`, `term_example_sentences`
- `questions` (MCQ/WRITE/FILL_IN_BLANK only — drop LISTEN)
- `user_term_stats`, `user_nodes`

New for v1:
- `accounts`, `sessions`, `verification_tokens` — Auth.js standard
- `jobs(id uuid, type text, status text, payload jsonb, result jsonb, error text, created_at, updated_at)` — async job tracking
- `deck_definitions(deck_id, definition_id, position int)` — junction

## 6. Core Flows

### 6.1 Add term + AI generation

1. User types term in deck UI → `POST /api/decks/:id/terms { value }` (web → pycil-core)
2. `pycil-core` checks cache (`terms.value` lookup); if hit → attach to deck, return 200.
3. If miss → INSERT `terms` row + `jobs(type=generate_term, status=pending)`, enqueue arq job.
4. Return `{ job_id }` to client (202 Accepted).
5. Client opens SSE: `GET /api/jobs/:job_id/stream` (web Next.js Route Handler).
6. `web` subscribes to Redis channel `results:{job_id}`.
7. `worker` consumes job → calls OpenRouter via LangChain → parses JSON → INSERTs `definitions`, `definition_paraphrases`, `term_example_sentences` → publishes to `results:{job_id}` → updates `jobs.status=completed`.
8. `web` forwards Pub/Sub message via SSE → client renders enriched term.

**Idempotency**: Redis lock `lock:generate_term:{term_value}` (NX, EX=300) prevents duplicate jobs.

### 6.2 Learning session

1. `POST /api/decks/:id/learn { session_size: 20 }` (web → pycil-core)
2. `pycil-core` selects M terms (priority: due → new → upcoming), creates Redis session state, returns `session_id`.
3. Per round (P=5 terms): client `GET /api/sessions/:id/question` → returns next question (from `questions` table or enqueues `generate_question` job if cache miss).
4. Client answers → `POST /api/sessions/:id/answer` → `pycil-core` updates round state, ELO computed at end-of-term (after Q correct first answers).
5. ELO update uses idea.md formulas: `Δ = K·(R-E)·T`, `I_new = I_old · F^((elo_new-elo_old)/S)`.
6. `next_review_date` snapped to nearest predefined interval (15min, 30min, ..., 2 months).
7. End of session → return summary, write `user_term_stats`.

## 7. Identified Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| ELO formula edge cases (cold start, division by zero, runaway scores) | High | Unit tests for boundary values; clamp ELO to [0, 3000]; use `idea.md` formulas as-is, validate with synthetic user |
| LangChain breaking changes | Medium | `LLMClient` abstraction; pin minor version; swap to litellm if blocked |
| LLM JSON schema drift (parse failures) | High | Pydantic models for LLM output; retry with stricter prompt; log failed payloads |
| Auth.js + FastAPI session sharing | Medium | Both read same `sessions` table; FastAPI parses `next-auth.session-token` cookie or accepts JWT issued by Next.js |
| Day-5 ELO + UI compression | High | Schedule ELO core (no UI) on Day 4 evening; UI Day 5 |
| Docker Compose on single VPS = single point of failure | Accepted | Out of scope for v1; address post-launch |
| OpenRouter cost spike | Low | Use cheap models (Gemini Flash, Claude Haiku); rate-limit per user (5 generations/min); $20 prepaid cap |
| 11 mastery levels mapping from ELO | High | Canonical mapping table lives in `phase-05-learning-mode-elo.md` (non-uniform buckets centered at ELO=1000). Test transitions during ELO unit tests. |

## 8. Success Criteria (Definition of Done)

End of Day 7:
- Public hosted URL with TLS
- Real Google OAuth sign-up flow
- User can create folder/deck, add 5+ terms, see LLM-generated content stream in
- User can run a learning session, answer questions, see ELO + next-review update
- Sentry-style error visibility (logs in `docker compose logs` minimum)
- Show HN / Product Hunt-ready landing page
- README with setup + architecture diagram

## 9. Conscious Tradeoffs

- **No tests during sprint** — rely on Opus 4.7 + manual smoke. Add tests post-launch.
- **No backups during sprint** — accept data loss risk for 1 week.
- **No monitoring** — use VPS provider dashboard + `docker logs`.
- **No CI/CD beyond deploy** — no preview envs, no rollback automation.
- **Mastery levels coupled to ELO** — explicit ELO→level mapping table is **canonical in `phase-05-learning-mode-elo.md`** (11 buckets with non-uniform ranges centered at ELO=1000). If ELO needs tuning post-launch, level boundaries shift in that file (acceptable).

## 10. Open Questions

- ELO→mastery-level mapping function: **resolved — see canonical 11-bucket table in `phase-05-learning-mode-elo.md`** (non-uniform ranges centered at ELO=1000).
- Question generation strategy: pre-generate all 3 types per definition, or on-demand at session time? **Tentative: on-demand with cache.**
- Where does Auth.js session cookie live for FastAPI to validate? **Tentative: shared `sessions` table read by SQLModel.**
- LangChain version pin: 0.3.x or 0.2.x? **Decide at scaffolding time.**

---

**Next:** see `docs/project-roadmap.md` for day-by-day plan.
