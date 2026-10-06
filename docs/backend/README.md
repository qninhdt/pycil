# Backend documentation

This documentation describes the backend contract completed on 2026-10-06.
It is not a deployment announcement. [Implementation status](implementation-status.md)
records evidence and external gates.

## Read by task

Final local checks and phase-to-test mapping: [verification record](verification.md).

| Task | Start here |
| --- | --- |
| Run the backend locally | [Getting started](getting-started.md) |
| Understand process and module boundaries | [Architecture](architecture.md) |
| Understand persistence and indexes | [Data model](data-model.md) |
| Configure an installation | [Configuration](configuration.md) |
| Integrate an API client | [API conventions](api-conventions.md), then the relevant module |
| Implement retained FE screens | [Frontend handoff](frontend-handoff.md) |
| Work on identity, settings, or allowances | [Account](modules/account.md) |
| Work on hierarchy, publication, or deck editing | [Library](modules/library.md) |
| Work on dictionary content and generation | [Vocabulary](modules/vocabulary.md) |
| Work on preparation, grading, and progress | [Study](modules/study.md) |
| Work on conversations and approvals | [Assistant](modules/assistant.md) |
| Deploy or diagnose a service | [Deployment](operations/deployment.md) |
| Upgrade or recover a database | [Migrations](operations/migrations.md) |
| Verify a change | [Testing](testing.md) |
| Implement the remaining redesign and FE APIs | [Consolidated implementation plan](implementation-plan.md) |

## Current inventory

- One Python application under `apps/api`, with API and worker entry points.
- Five business modules: account, library, vocabulary, study, and assistant.
- 37 business API operations; `/health` and `/ready` are operational routes.
- PostgreSQL schemas `public`, `lexi`, and `checkpoints`, with separate DDL ownership.
- Redis for optional cached values and required coordination.
- A local vendored Lexi wheel, an external read-only Cambridge SQLite artifact, and
  configured inference/decision services.
- Node FTS/Discovery, atomic reviews, durable activity and jointly bounded summaries.
- No integrated product FE client or Star/Pin/tag/translation/import/audio subsystem.
  Local `apps/web` starter/showcase work is not an approved integration target.

## Sources of truth

1. Routes and request/response models define the current HTTP contract.
2. Service functions and tests define current behavior, including failures.
3. Historical migrations define upgrade transformations; ORM metadata defines current schema.
4. `config/config.yaml` defines product policy; deployment environment supplies addresses and secrets.
5. These pages explain the relationships and operational consequences.

The running application serves `/openapi.json`, `/docs`, and `/redoc`. Prefer generated
OpenAPI for exact field types and required fields. Examples here are complete requests
or explicitly illustrative fragments, not an alternative schema specification.

## Maintaining these pages

Update the relevant module, configuration/data-model page, tests, and implementation
status together when changing a contract. Do not describe a proposed endpoint as
available. Do not copy old frontend plans into current documentation as evidence.
Keep product requirements out of implementation explanations and put technical notes here.

Source references are relative links to the repository. Test names are evidence of
behavior, not promises about production throughput. See [implementation status](implementation-status.md)
and [testing](testing.md) for verification scope and limitations.
