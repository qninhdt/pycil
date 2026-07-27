# Canonical Inventory — 2026-07-18

## Frozen product decisions

- Pycil is a backend-only FastAPI API, arq worker and shared Python package.
- The external client is Next.js with `iron-session`; Pycil receives bearer
  tokens only from the BFF.
- Lexi runs as a separate PostgreSQL-backed service. Pycil never imports its
  ORM or uses a local Lexi SQLite database.
- Public nodes are readable by anyone; private nodes are author-only. Mutation
  remains author-only.
- There is no production data. Unsupported schema may be removed without
  backfill or compatibility shims.

## Runtime inventory

| Surface | Classification | Evidence / action |
|---|---|---|
| FastAPI, arq, shared-py | KEEP | Canonical Pycil runtime. |
| OAuth bearer, hierarchy, FSRS, Centrifugo, bounded assistant | KEEP/COMPLETE | Complete missing frontend-facing contracts in later phases. |
| In-process `Lexicon` path dependency | MIGRATE | Replace with a typed Lexi service client. |
| `UserRole`, role claim and `require_admin` | DELETE | No canonical admin product. |
| Notification channel/payload | DELETE | No notification product. |
| `UserNode`, star/pin, social counts and folder attributes | DELETE | No caller in canonical product. |
| `nodes.sense_count` | DELETE | Compute current counts in queries. |
| Billing, gamification, ELO, translation, TTS, general SSE | DELETE | Explicitly outside canonical scope. |

## Canonical data ownership

| Store | Owner | Kept data |
|---|---|---|
| Pycil PostgreSQL | Pycil | identity, hierarchy, deck membership, FSRS, responses, assistant state |
| Lexi PostgreSQL | Lexi service | generated entries, senses, questions, durable Lexi jobs |
| Cambridge artifact | Lexi service, read-only | versioned reference SQLite artifact, downloaded/cached outside Git |
| Redis | coordination only | arq, queues, cache and stream delivery; rebuildable |

## Required contracts not present yet

- `GET /v1/me`; canonical camelCase/error response envelope.
- Hierarchy roots, children, detail, ancestors and metadata update routes.
- Word search, durable Pycil orchestration jobs and poll/result route.
- Lexi service sense resolution, question generation/get/grade/list and
  terminal job result contract.
- Cursor pagination for growing lists and typed question payloads.

## Baseline and destructive-work assumptions

- Preserve existing dirty user changes: `.gitignore`, architecture/changelog
  docs, agent configuration and untracked journals were not modified by this
  phase.
- API/shared/worker test and Compose/migration commands are rerun as each
  affected phase lands; no secret values or dataset content is recorded here.
- Account banning is removed with role/admin state: no operator ban workflow
  exists in the canonical product. `token_version` remains the sole token
  revocation mechanism.

## Historical allowlist

- Git history and `docs/project-changelog.md` retain historical claims.
- Existing Alembic history may remain only as non-normative history until the
  no-production-data canonical baseline migration is established.
- The canonical plan is the sole active execution plan; old feature plans are
  sources or superseded artifacts, never runtime specifications.
