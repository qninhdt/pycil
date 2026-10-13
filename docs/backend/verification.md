# Consolidation verification

The backend implementation of the approved [redesign](../../redesign.md) is complete. This record covers
local backend checks, not deployment or frontend acceptance. The old backend suite was
deleted without reading it; current tests were written from behavior and source contracts.

## Verified behavior

| Boundary | Evidence |
| --- | --- |
| Fresh schema and ORM agreement | [Real PostgreSQL comparison](../../apps/api/tests/integration/infrastructure/test_schema.py) |
| JSONL import | [Identity, replay, conflicts and atomicity](../../apps/api/tests/integration/vocabulary/test_reference_import.py) |
| Generation/search | [Evidence validation, incremental visibility and failed-index retry](../../apps/api/tests/integration/vocabulary/test_generation.py) |
| Job ownership | [Singleflight and cancellation](../../apps/api/tests/unit/vocabulary/test_jobs.py) |
| Relations/themes/translation | [Vocabulary integrations](../../apps/api/tests/integration/vocabulary/), [theme namespaces](../../apps/api/tests/integration/themes/test_namespaces.py) |
| Artifact banks and grading | [Study integrations](../../apps/api/tests/integration/study/) |
| Atomic progress | [Review replay/concurrency and rollback](../../apps/api/tests/integration/study/test_reviews.py) |
| Identity/account | [JWT validation, concurrent provisioning and failed remote lookup](../../apps/api/tests/integration/account/test_identity.py), [settings](../../apps/api/tests/integration/account/test_settings.py), [usage](../../apps/api/tests/integration/account/test_usage.py) |
| Publication/access | [Live revocation and private access](../../apps/api/tests/integration/library/test_publication.py) |
| Native conversation storage | [Checkpoint restart, ownership and lease](../../apps/api/tests/integration/assistant/test_checkpoints.py) |
| Lifecycle | [Real startup/readiness and cleanup after partial failure](../../apps/api/tests/integration/app/test_lifespan.py) |
| HTTP boundary | [Streamed body cap, sanitized errors and correlation](../../apps/api/tests/unit/app/test_http.py) |
| Typed cache | [Real Redis TTL, invalidation, corrupt JSON and wrong Redis types](../../apps/api/tests/integration/infrastructure/test_cache.py) |
| Operation observations | [Failure/cancellation propagation and context restoration](../../apps/api/tests/unit/infrastructure/test_observability.py), [provider cancellation without retry](../../apps/api/tests/unit/infrastructure/test_llm.py) |

Integration stores come from Testcontainers. External identity/model services are
controlled at their transport boundary; signature checks, business validation, database
transactions, Redis coordination and Tantivy stay real where exercised.

## Artifact checks

The complete reference JSONL was validated, imported and reimported into a disposable
PostgreSQL database. Its [manifest](../../data/reference.manifest.json) records counts
and checksum. Regular tests use compact valid fixtures instead of loading the full corpus.

The application wheel was rebuilt after the Pydantic decision migration. It includes all
16 remaining local prompt assets and no retired decision JSON templates or SQLite files.
The earlier Docker image build and quiet Compose validation used placeholder credentials;
they were not repeated for the provider migration.
The initial 50-case result predates the additional [test plan](../../test.md) and is not
evidence that the expanded plan is complete. Resource startup and identity callers use the user-updated typed Redis adapter;
the obsolete constructor argument and unused admission/value-size settings were removed.
[OpenAPI](openapi.json) exports without resource/provider startup. Exact test results
are reported with each implementation turn rather than inherited from the deleted suite.

## Additional test execution

Status: the additional test inventory remains in progress. The current full unit run on
2026-10-13 passed **251 cases** in 8.57 seconds. The final full integration rerun passed
**142 cases** in 82.68 seconds after the runtime client rename and timeout/logging fixes.
Its 12 warnings come from AG-UI's deprecated LangGraph schema method and were not
suppressed. Counts describe collected cases, not coverage percentages.

The transitional Instructor collection failures are resolved. Grading and relation
selection now use native Pydantic Decisions models, without JSON-e or legacy fallback
contracts. Structured generation uses Instructor's parser and reask feedback with one
bounded retry policy; SDK transport retries are disabled. Tests exercise actual native
clients against controlled HTTP transport, including transient statuses, invalid choices,
refusal, truncation, failed-attempt usage, cancellation, whole-operation deadline,
concurrent usage isolation and sanitized native retry logs. The log regression failed
before the fix because Instructor included the raw model output in its validation error.

Focused provider/model verification passed **54 cases** in 7.75 seconds. Ruff passed on
all production/test files touched by the provider migration and runtime client rename.
Strict Pyright passed with **0 errors** for infrastructure `llm.py` and the study/relation
decision model modules. This is a scoped result, not a full backend typing acceptance.

The following records link specific new scenarios to their focused execution evidence.
Parameterized scenarios share one node where each parameter protects a distinct outcome.

| Behavior | Concrete scenario | Layer | Assertion | Action | Evidence |
| --- | --- | --- | --- | --- | --- |
| Single-word grading | Exact alternate word; fuzzy spelling; matched meaning but poor task fit | Integration | Native Tantivy resolves the alternate Sense and diagnostics preserve fit/spelling | Extend | [test_grading_branches.py](../../apps/api/tests/integration/study/test_grading_branches.py), `test_single_word_grading_resolves_alternate_meaning_through_real_search`; 3 passed |
| Unanswered grading | Single-word, definition, usage and rewrite | Integration | Unused diagnostic shape; an empty provider script proves no inference occurs | Extend | Same file, `test_null_answer_returns_unused_diagnostics_without_inference`; 4 passed |
| Grading failure | Missing artifact, incompatible kind, single-choice, missing definition, failed provider | Integration | Correct exception; no new definitions, memory or review receipts | Extend | Same file, `test_grading_failures_do_not_publish_content_or_learning_state`; 5 passed |
| Alternate review credit | Spelling-error answer matches a different word | Integration | Alternate Sense receives memory, recall 1 and performance 0.8; target remains unstudied | Extend | [test_reviews.py](../../apps/api/tests/integration/study/test_reviews.py), `test_alternate_word_credit_and_cross_word_definition_rejection_are_atomic`; passed |
| Definition review validation | Valid alternate answer plus invalid cross-word definition in one batch | Integration | Entire batch rejects before memory, receipt or activity writes | Extend | Same node; passed |
| Grouped reviews/activity | Repeated artifact with correct and incorrect answers; acceptance crosses Vietnamese midnight | Integration | One memory/activity update, two evidence records, latest exposure and acceptance-day bucket | Extend | Same file, `test_repeated_artifacts_share_one_update_and_acceptance_timezone`; passed |
| HTTP entitlement | Free denied; persisted upgrade to Pro accepted | Integration | Actual ASGI request returns 403 then typed 200 diagnostics | Extend | [test_routes.py](../../apps/api/tests/integration/app/test_routes.py), `test_study_http_grading_rechecks_plan_and_review_header_controls_replay`; passed |
| HTTP grading errors | Missing artifact and provider failure | Integration | 404/503 domain translation; private exception marker omitted | Extend | Same node; passed |
| HTTP review identity | Missing header, identical keyed replay, changed keyed payload | Integration | 422/200/409; one persisted review count | Extend | Same node; passed |
| Hydration limits | Two complete meanings at cap; cap exceeded; missing word | Integration | Complete groups and bounded examples, explicit errors rather than silently truncated meanings | Extend | [test_content.py](../../apps/api/tests/integration/vocabulary/test_content.py), `test_word_preview_hydration_keeps_complete_groups_and_rejects_overflow`; passed |
| Personal projections | Same vocabulary, two users, one private deck/memory | Integration | Other user receives new state and no private sources; duplicate context IDs rejected | Extend | Same file, `test_viewer_context_never_reuses_another_users_memory_or_private_sources`; passed |
| Root authorization | Private/public nodes have deliberately incorrect space labels | Integration | Owner/private access remains; foreign and anonymous visibility follows physical roots; breadcrumbs exclude private ancestors | Add | [test_access.py](../../apps/api/tests/integration/library/test_access.py), `test_visibility_uses_live_root_paths_and_public_breadcrumbs`; passed |
| Damaged ancestry | Deleted ancestor or absent library-root closure path | Integration | Even owner reads return `node_not_found` | Add | Same file, `test_broken_physical_ancestry_denies_even_owner_reads`; 2 passed |
| Assistant HTTP stream | Actual authenticated ASGI run against native graph/checkpointer | Integration | SSE status, buffering headers, run lifecycle and persisted assistant response | Add | [test_http.py](../../apps/api/tests/integration/assistant/test_http.py), `test_conversation_http_stream_state_pagination_and_delete_enforce_ownership`; passed |
| Conversation ownership | Foreign run/read/delete and foreign pagination cursor | Integration | 404/422; owned state read incurs no extra settlement; deletion removes native checkpoint | Add | Same node; passed |
| Dependency readiness | Native PostgreSQL/Redis authentication failure | Integration | Safe 503 under the runtime deadline; health remains available and owned resources close | Extend | [test_lifespan.py](../../apps/api/tests/integration/app/test_lifespan.py), `test_readiness_dependency_failures_return_safe_503_and_preserve_health`; 2 passed |
| Shutdown ownership | Generation paused at external enrichment when shutdown begins | Integration | Cancellation joins while HTTP, search, Redis and PostgreSQL remain usable; no partial word; clients close afterward | Extend | Same file, `test_shutdown_joins_generation_before_closing_its_native_dependencies`; passed |
| Invalid metering details | Empty list, false and zero supplied instead of a details object | Unit | No fabricated charge; one unmetered call | Extend/fix | [test_metering.py](../../apps/api/tests/unit/assistant/test_metering.py), `test_invalid_measurements_are_unmetered_instead_of_fabricated`; all 3 failed before the fix; focused rerun recorded below |

Focused execution: grading **17 passed**, reviews **5 passed**, HTTP routes **3 passed**,
content/access **6 passed**. Assistant streaming **10 passed**, including fresh auto-approve
settings, quota enforcement and refusal to auto-execute an already pending approval.
Assistant HTTP **1 passed**; lifecycle/readiness **6 passed** plus the shutdown case **1 passed**.
After the metering fix, its focused unit group passed **13 cases** in 0.02 seconds;
Ruff lint and formatting passed for that production file and its tests.
Native AG-UI emits a LangGraph schema-method deprecation warning; it was not suppressed.

### Remaining verification work

The table above records this execution batch, not every case in the target inventory.
Completion still requires reconciling the entire inventory with retained tests, extending
remaining operation-specific adapter cases where missing,
and recording the final complete runs after all additions. Infrastructure
decision cases must follow the current Instructor implementation; removed Choice fallback
and JSON-repair machinery must not be restored merely to satisfy obsolete plan wording.

The scoped provider typecheck and wheel rebuild passed as recorded above. No full backend
typecheck, Docker image rebuild or deployment check was repeated for this test expansion
while another session was modifying Python typing.

## Limits

Frontend changes and browser E2E are outside the current backend work. Tests do not call
live Clerk or paid model providers. No production migration, deployment, restore rehearsal,
or production capacity/load measurement has been performed. OpenTelemetry exporters and
Langfuse remain deferred. There is no backend system/performance/E2E suite.
