# Pycil

Pycil is a subscription vocabulary learning platform designed to help learners collect, organize, and practice English meanings at their own pace. It pairs a **Next.js 16** frontend with a **FastAPI (Python 3.14)** service, utilizing the **FSRS** (Free Spaced Repetition Scheduler) algorithm, Tantivy full-text search, and AI-assisted dictionary generation.

---

## Architecture Overview

```
                                      ┌────────────────────────┐
                                      │   Web Client (Next.js) │
                                      │   Port 3000 / Vercel   │
                                      └───────────┬────────────┘
                                                  │ HTTPS
                                                  ▼
                                      ┌────────────────────────┐
                                      │    Caddy TLS Ingress   │
                                      │     Port 80 / 443      │
                                      └───────────┬────────────┘
                                                  │ HTTP
                                                  ▼
                                      ┌────────────────────────┐
                                      │   Pycil API (FastAPI)  │
                                      │  Python 3.14 / Uvicorn │
                                      └─────┬───────┬───────┬──┘
                       ┌────────────────────┘       │       └───────────────────┐
                       ▼                            ▼                           ▼
            ┌────────────────────┐       ┌────────────────────┐      ┌────────────────────┐
            │   PostgreSQL 18    │       │      Redis 8       │      │   Tantivy Index    │
            │ Authoritative Data │       │   Sessions & Jobs  │      │  Local Search FTS  │
            └────────────────────┘       └────────────────────┘      └────────────────────┘
```

### Core Technologies

- **Backend (`apps/api`)**: Python 3.14, FastAPI, SQLAlchemy 2.1 (asyncio + asyncpg), Pydantic v2, Tantivy (full-text search), `fsrs-rs-python` (spaced repetition), LangGraph, Instructor and native Taskiq workers. Managed with [`uv`](https://github.com/astral-sh/uv).
- **Frontend (`apps/web`)**: Next.js 16 (App Router), React 19, Tailwind CSS v4, `@shadcn/react`, TanStack Query & Table, `@assistant-ui/react`, next-intl. Managed with `pnpm`.
- **E2E Testing (`e2e`)**: Independent Playwright test suite for critical learner and authentication journeys.
- **Data & Storage**: PostgreSQL 18 with single baseline migrations (Alembic), Redis 8 for coordination and session caches.
- **Operations & DevOps**: Docker Compose, Caddy reverse proxy with automated TLS, WAL-G automated backups, LGTM observability pipeline.

---

## Repository Structure

```text
.
├── apps/
│   ├── api/                   # FastAPI backend service (Python 3.14, uv)
│   │   ├── pycil/             # Core application domains (account, library, vocabulary, study, assistant)
│   │   ├── migrations/        # Alembic database migrations
│   │   └── tests/             # Unit and integration test suites
│   └── web/                   # Next.js 16 web application
│       ├── src/               # React 19 App Router components, hooks, and feature modules
│       └── tests/             # Unit and browser integration tests (Vitest, Playwright)
├── e2e/                       # Independent end-to-end integration and Playwright journey suite
├── config/                    # Canonical system policy configuration (config.yaml)
├── data/                      # Reference dictionary artifacts and manifest (JSONL.gz)
├── devops-course/             # 26-lesson guided practical DevOps course and lab environments
├── docs/                      # Technical documentation
│   ├── backend/               # Architecture, API conventions, modules, operations
│   └── devops-architecture/   # Infrastructure, 12-factor design, hybrid VPS/AWS specs
├── scripts/                   # Tooling scripts (compose.py, deploy.sh, export_openapi.py)
├── Caddyfile                  # Production & staging Caddy ingress rules
├── docker-compose.yml         # Local & deployment Docker Compose stack
├── Makefile                   # Unified developer workflow commands
├── PRODUCT.md                 # Product requirements and learner experience specification
└── DESIGN.md                  # Visual design system, color palette, and component tokens
```

---

## Quick Start

### Prerequisites

- **Python**: `>= 3.14` (installed via `uv python install 3.14.8`)
- **uv**: `>= 0.12`
- **Node.js**: `>= 24.21.0`
- **pnpm**: `>= 12.9.1`
- **Docker**: Engine with Compose v2

### 1. Backend Setup

```bash
cd apps/api
cp ../../.env.example .env     # configure secrets
uv sync --locked
uv run --locked uvicorn pycil.main:app --reload
```

Or run via `Makefile`:

```bash
make api-dev
```

Word generation and study preparation also need the separate [Taskiq worker](docs/backend/modules/jobs.md#native-worker-command); worker deployment is not yet part of Compose.

The API will be available at `http://localhost:8000`. Swagger documentation is served at `/docs`.

### 2. Frontend Setup

```bash
cd apps/web
cp .env.example .env.local    # configure Clerk publishable key & API URL
pnpm install
pnpm run dev
```

The frontend will be available at `http://localhost:3000`.

### 3. Running with Docker Compose

To start the full local stack (PostgreSQL, Redis, Migrations, API, Caddy):

```bash
make docker-up
```

To shut down:

```bash
make docker-down
```

---

## Quality & Testing

### Backend Quality Gates

```bash
# Linting & Formatting checks
make lint

# Run all backend tests
make test

# Fast unit tests
make test-unit

# Database & service integration tests (requires Docker / Testcontainers)
make test-integration
```

### Frontend Quality Gates

```bash
cd apps/web

# TypeScript typecheck
pnpm run typecheck

# Linter (Oxlint)
pnpm run lint

# Unit tests
pnpm test:unit

# Component and service integration tests
pnpm test:integration
```

### E2E Quality Gates

```bash
cd e2e

# Typecheck and isolated support checks
pnpm typecheck
pnpm test:support
```

---

## Documentation Index

- [**Product Specification**](PRODUCT.md): User personas, learning mechanics, and product principles.
- [**Design System**](DESIGN.md): Typography, color palette tokens, and UI layout conventions.
- [**Search & Content Revisions Architecture**](search_and_content_revisions.md): PostgreSQL revision tables and Tantivy indexing model.
- [**Backend Architecture & APIs**](docs/backend/README.md): Domain models, data flow, HTTP conventions, and deployment guides.
- [**DevSecOps Architecture**](docs/devops-architecture/00-architecture-overview-and-standards.md): Capacity models, infrastructure as code, CI/CD, and disaster recovery.
- [**DevOps Practical Course**](devops-course/README.md): 26 hands-on lessons with guided lab exercises.
