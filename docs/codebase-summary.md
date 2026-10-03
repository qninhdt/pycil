# Current backend layout

| Path | Purpose |
| --- | --- |
| `apps/api/pycil/account` | Clerk identity/lifecycle, one JSONB settings object, plans and units |
| `apps/api/pycil/vocabulary` | Native Lexi reads, selected shared generation request/status/execution |
| `apps/api/pycil/library` | Live owner/public/reference access, folder/deck tree, batched membership |
| `apps/api/pycil/study` | Read-only preparation, native diagnostics, Sense rating/FSRS/history/progress |
| `apps/api/pycil/assistant` | Native graph/checkpoints, AG-UI approval/streaming, tools, metering/retention |
| `apps/api/pycil/worker.py` | One advisory-lock-owning generation/retention process |
| `apps/api/pycil/migrate.py` | Explicit ordered schema gate; never called at runtime |
| `apps/api/migrations` | Frozen Pycil-only `0001_initial` schema |
| `apps/api/tests` | Fresh unit/integration/system behavior gates; no archived test compatibility |
| `config/config.yaml` | Validated shared product policy, not secrets |
| `vendor/lexi-ai` | Unpublished local enum-capable wheel, hashes, provenance and rebuild instructions |
| `scripts` | Guarded operator deploy/fresh rehearsal and deterministic library packaging |

`apps/web` is intentionally absent. Older plans/designs/journals/analysis reports
are historical, not current implementation instructions. Old backend/tests live
in the verified external archive, outside imports, discovery and Docker context.

See [architecture](system-architecture.md), [testing](testing-setup.md) and
[execution checkpoint](backend-rewrite-status.md).
