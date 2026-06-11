# Pycil

AI-powered vocabulary learning with ELO-driven spaced repetition.

- **PDR:** [`docs/project-overview-pdr.md`](docs/project-overview-pdr.md)
- **Roadmap:** [`docs/project-roadmap.md`](docs/project-roadmap.md)
- **Active plan:** [`plans/260525-0124-pycil-mvp-implementation/plan.md`](plans/260525-0124-pycil-mvp-implementation/plan.md)

## Architecture

Three services on a single VPS via docker-compose:

```
[Browser]
   └── Caddy (TLS) ─┬─> web         (Next.js 15 + Auth.js v5, port 3000)
                    ├─> pycil-core  (FastAPI + SQLModel, port 8000)
                    └─> worker      (Python arq + LangChain → OpenRouter)
                          ├─ Postgres 16
                          └─ Redis 7
```

## Local development

Prereqs: Docker 24+, docker-compose v2, a Google OAuth client, an OpenRouter API key.

```bash
cp .env.example .env
# Fill in: AUTH_SECRET (openssl rand -base64 32), GOOGLE_CLIENT_ID,
# GOOGLE_CLIENT_SECRET, OPENROUTER_API_KEY.

# Select the dev Caddyfile (Caddy internal CA, never burns Let's Encrypt rate
# limit) via env — no destructive copy over the tracked prod Caddyfile.
export CADDYFILE=./Caddyfile.local

docker compose up --build
```

Run the initial migration (one-shot, against the running pycil-core image):

```bash
docker compose run --rm pycil-core alembic upgrade head
```

Visit https://localhost (accept the Caddy internal-CA warning) → sign in with Google → land on `/dashboard`.

## Production deploy

GitHub Actions (`.github/workflows/deploy.yml`) handles build + SSH deploy on push to `main`. Required secrets:

- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`

Deploy order is **migration-then-swap**:

1. `pg_dump` snapshot to `/var/backups/pycil/pre-deploy-<ts>.sql` (last 5 kept).
2. `docker compose pull` new images.
3. `alembic upgrade head` in a one-shot container against the new pycil-core image.
4. On migration success only: `docker compose up -d`.
5. Health-check loop on `web` and `pycil-core`.

Rollback: `alembic downgrade -1` then `docker compose pull <previous-tag> && docker compose up -d`. If schema diverged irrecoverably, restore from the latest `pre-deploy-*.sql`.

## Admin dashboard

The `/admin` surface (users, reports, metrics, spend, flags, health, audit) is gated by `users.role`. There is no UI to grant admin — seed the first admin directly via SQL:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

The backend re-reads `users.role` on every request (the JWT `role` claim is edge-convenience only), so a freshly promoted admin reaches `/admin` on their next login.

**Rollback ordering for migration 0019 (`user_role_and_ban`):** `get_current_user` does `SELECT … role FROM users` on every authenticated request. If you `alembic downgrade -1` past 0019 while the new image is still live, the dropped `role` column 500s every authed request. **Swap the image back to a pre-0019 build BEFORE downgrading 0019** (or treat 0019's column-drop as a no-op). The same applies to 0020/0021 only in that they must be downgraded in reverse order (0021 → 0020 → 0019).

## Repo layout

```
apps/
  web/         Next.js 15 + Auth.js v5
  pycil-core/  FastAPI + SQLModel + Alembic
  worker/      arq + LangChain (filled in phase 3)
docs/          PDR + roadmap
plans/         Implementation plans
Caddyfile      Production reverse proxy
Caddyfile.local Dev reverse proxy with internal CA
docker-compose.yml
```

## v1 scope

Google sign-in · folders + decks · LLM-generated definitions/paraphrases/examples · MCQ + Write + Fill-in-blank questions · ELO learning sessions · 11 mastery levels · public/cloned decks · TTS audio · definition translation · Sentry + OpenTelemetry tracing (opt-in) · opt-in restic backups.

Removed in rehab (deliberate — not deferred): SHORTCUT nodes · definition topic/usage tags · i18n · payments/premium · mobile native · Loki/Tempo/Grafana log+metrics stack.
