# Completion verification record

Archived record. Current-only baselines and targeted Library mutations supersede the migration/editor contracts below; see [current setup](operations/migrations.md) and [OpenAPI](openapi.json).
Date: 2026-10-06. Backend based on `e79a53c`; no deployment or production migration
performed. This covers the reduced **backend** delivery, not live FE/provider
acceptance or production capacity certification.

## Final executable results

| Check | Result |
| --- | --- |
| `make lint` | Ruff lint passed; 81 files formatted |
| `make test-unit` | 103 passed in 5.61 seconds; subset of the full suite |
| `make test-api` | **240 passed, 1 skipped** in 83.66 seconds after search optimization |
| Small matrix | 1 passed in 46.14 seconds; 30 workloads / 167 JSON plans |
| Medium matrix | 1 passed in 55.98 seconds; 30 workloads / 167 JSON plans |
| Migration/drift | Passing suite covers fresh/repeated Lexi -> Pycil -> checkpoints and populated 0001/0002 upgrades |
| OpenAPI | 37 operations exported without startup; checked against the imported app schema |
| Wheel | Built; every packaged runtime source matches the working tree, tracked prompt present, local prompt absent |
| Runtime/test Compose | Both quiet validations passed with dummy endpoints / no runtime `.env` |
| Deployment shell | `bash -n scripts/deploy.sh` passed; script not executed |
| Caddy | Pinned 2.11.6 validation passed; no deployed ingress |
| Documentation / diff | Relative backend links resolve; `git diff --check` passed; historical revisions unchanged |

The sole skip is the opt-in benchmark; small/medium passed separately, large was not
run. Eleven warnings are the upstream AG-UI/LangGraph `get_config_jsonschema`
deprecation. Each managed run cleaned its own stores/network. Tests require no
application `.env`, manual database/Redis URLs or paid inference.

Wheel: `/tmp/opencode/pycil-completion-build/pycil_api-1.0.0-py3-none-any.whl`.
SHA-256: `abd24fa15e628f7f7231a086bdf72ff3780b0a3dca4d44a13e6f6c56303b5631`.
Only verified wheel-generated `apps/api/build` copies were removed after comparison.
Historical 0001/0002 revisions, deleted legacy docs and unrelated user work are preserved.

## Acceptance traceability

| Phase | Executable / handoff evidence |
| --- | --- |
| 0 Contract | [Strict DTO/hash/cursor tests](../../apps/api/tests/unit/test_completion_contracts.py), [HTTP/OpenAPI](../../apps/api/tests/system/test_http_boundary.py) |
| 1 Migration | Learning upgrade (historical, removed), placement (historical, removed), [fresh drift](../../apps/api/tests/integration/test_fresh_schema.py) |
| 2 Batch/activity | [Completion cases](../../apps/api/tests/integration/test_completion.py): failure/replay/locks/DST/midnight/revocation/cascades; [native rating/equality/practice](../../apps/api/tests/integration/test_learning_pipeline.py) |
| 3 Prepare | [Native generation/storage/selection/short-circuit/readiness/entitlement/grading](../../apps/api/tests/integration/test_learning_pipeline.py) |
| 4 Reporting | [Partitions, grids, streaks, timezone/membership/schedule](../../apps/api/tests/integration/test_progress.py); joint counts/logical bounds/shared deadlines in completion cases |
| 5 Browse | Completion cases: opaque/deleted-anchor cursors, literal lemma, review/null order, native examples and source overflow |
| 6 Search | Completion cases: FTS weights/rename/mixed-language, public path corruption, filter binding and revocation |
| 7 Dictionary | Completion cases: complete batch hydration/bounds, memberships/aliases, private/remote/revoked/untracked state |
| 8 Profile | Contract/completion cases: concurrent uniqueness, ASCII/Unicode, bio omission/null, rename and guest privacy |
| 9 Assistant | [Approvals/reauthorization/stream/disconnect/ownership/restart](../../apps/api/tests/integration/test_assistant.py); shared read tools in completion cases |
| 10 Foundation | [Library](../../apps/api/tests/integration/test_library.py), parent-walk closure oracle/over-limit repair in completion cases, [timeout](../../apps/api/tests/integration/test_query_timeout.py), [bootstrap](../../apps/api/tests/integration/test_bootstrap.py), [process restart](../../apps/api/tests/system/test_process_restart.py) |
| 10 Query/load | [Opt-in harness](../../apps/api/tests/performance/test_read_matrix.py), [archived full plans and limits](operations/performance.md); 5/50-card summaries each use four SELECTs |
| 11 Handoff | [Screen/error/scenario guide](frontend-handoff.md), [exported schema](openapi.json), current English module/product/config/migration/deployment docs |

## Resolved failures and bounded conclusions

- Receipt hash ORM type matches migration TEXT; populated/fresh drift checks pass.
  Old head/table test assertions were updated, not historical migration transforms.
- Native EXPLAIN replay restores Lexi/public search paths. Deterministic benchmark
  output follows the installed anchored-question schema; native validation/storage
  stay real, with no paid-provider call.
- Inline search summaries reuse original scope work/deadline; regression proves no
  second physical expansion and no reset of an expired budget.
- Medium plans show no global scheduling/receipt sequential scan or temp block writes.
  Broad FTS is candidate-dependent; native refresh rebuilds the global dictionary
  index. Dictionary fixtures have only 1,000 senses. No larger-scale guarantee follows.

## External decisions

Four unchecked plan items concern large-tier resources, full target-environment metrics/
lock waits, approved capacity thresholds and FE recall-rating UI. They do not permit
inventing an SLA, running an unapproved large tmpfs load, mapping answer feedback to
recall ratings, overwriting the local web showcase or deploying production.

Agree the product FE target and integration-host inputs before live browser acceptance.
Sessions/drafts remain client-local. No deferred feature, telemetry/session subsystem
or new frontend scaffold was added merely to make the checklist appear complete.
