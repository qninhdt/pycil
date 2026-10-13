# Backend documentation

The backend is being consolidated according to [the redesign](../../redesign.md).
These pages describe the current rewrite. Local verification is recorded separately
from deployment and live-provider evidence.

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
| Plan VPS/AWS observability and deployment | [Platform design proposal](../operations/README.md) |
| Upgrade or recover a database | [Migrations](operations/migrations.md) |
| Verify a change | [Testing](testing.md) |
| Follow the approved consolidation | [Redesign](../../redesign.md) |

## Current inventory

- One Python application under `apps/api`, with an API entry point and finite migration gate.
- Six business domains: account, library, vocabulary, study, themes and assistant.
- 39 business API operations; `/health` and `/ready` are operational routes.
- PostgreSQL `public`, one application baseline and native checkpoint setup.
- Redis for optional cached values and required coordination.
- Application-owned vocabulary, immutable reference JSONL and configured model/decision services.
- Node FTS/Discovery, atomic reviews, durable activity and jointly bounded summaries.
- Product frontend under `apps/web` with live services and a root [product E2E](../../e2e/README.md)
  package; live execution remains an external verification gate. No Star/Pin/tag/
  translation/import/audio subsystem.

## Sources of truth

1. Routes and request/response models define the current HTTP contract.
2. Service functions and tests define current behavior, including failures.
3. The single application baseline initializes fresh databases; ORM metadata defines current schema.
4. `config/config.yaml` defines product policy; deployment environment supplies addresses and secrets.
5. These pages explain the relationships and operational consequences.

The running application serves `/openapi.json`, `/docs`, and `/redoc`. Prefer generated
OpenAPI for exact field types and required fields. Examples here are complete requests
or explicitly illustrative fragments, not an alternative schema specification.

## Maintaining these pages

Update the owning module or operational page when changing a durable contract. Do not describe a proposed endpoint as
available. Do not copy old frontend plans into current documentation as evidence.
Keep product requirements out of implementation explanations and put technical notes here.

Source references are relative links to the repository. Test names are evidence of
behavior, not promises about production throughput. See [verification](verification.md)
and [testing](testing.md) for verification scope and limitations.
