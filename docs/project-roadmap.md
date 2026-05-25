# Pycil — 7-Day Sprint Roadmap

**Sprint window:** 2026-05-25 → 2026-05-31 (Day 1 → Day 7)
**Target:** Public launch on Day 7
**Status:** v1 phases 1-7 completed (live launch event still pending — see Phase 7).
**See also:** `docs/project-overview-pdr.md`, `docs/codebase-summary.md`, `docs/system-architecture.md`, `docs/project-changelog.md`, `plans/idea.md`, `plans/260525-0124-pycil-mvp-implementation/plan.md`

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
- Playwright E2E suite (auth-flow, create-deck-and-term, learn-session, chat-mode, test-mode, sign-out-everywhere)
- `last_llm_response` retry idempotency wired into worker code paths
- OpenRouter model fallback chain implementation
- Caddy `@sse` matcher widened to `/chat/sessions/*/stream`
- LLM-as-judge tier-4 grading (currently disabled via `use_llm_fallback=False` default)
