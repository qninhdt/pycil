# Test classification inventory

Every test file that existed before this phase, what happened to it, and why. The
column that matters is **level**: it is assigned by what the test actually exercises,
not by the folder it happened to sit in.

Counts: **41 files moved** to a level, **40 new test files** (plus `__init__.py` markers
and the shared support modules), and **49 files retired** — 9 of those by this phase,
the rest by the earlier cutovers. The full tree is verified green at each level:
API 473 passed / 1 skipped, worker 23 passed / 4 skipped, web 114 passed.

## Retired before this phase (Phases 03–05)

These deletions belong to the Clerk, Redis-broker and hierarchy cutovers. They are
recorded here because a reader of this phase's diff sees them and needs to know they
were already accounted for, not dropped silently.

| Retired file(s) | What it asserted | Why it is gone |
|---|---|---|
| `tests/auth/{test_tokens,test_oauth,test_refresh_coordination,test_dev_identity,test_current_user}.py` | Pycil's own access/refresh JWT minting, OAuth callback, refresh coordination, dev identity, `current_user` | Clerk issues and refreshes sessions now. `pycil.auth.dev_identity` no longer exists, so these could not run. Replaced by `integration/auth/test_clerk_identity.py`. |
| `tests/realtime/*` (4 files) | SSE channel tokens, subscribe proxy, realtime control boundary | Realtime delivery was retired; the assistant streams over AG-UI instead. |
| `tests/tasks/*` (3 files) | PostgreSQL task registry, submit-or-join, dispatch retry bounds | The DB queue overlay was replaced by Taskiq Redis Streams. Replaced by `integration/queue/test_job_receipt_ownership.py` and the worker's integration suite. |
| `tests/contracts/*` (5 files) | Design/learning/statistics contract gaps, response camel-case, route auth coverage | These asserted the *absence* of a bug found by reading a schema, not behaviour. The properties they guarded now have behavioural owners: camel-case aliases by the integration route tests, route auth by `integration/content/test_word_search_auth_boundary.py`. |
| `tests/account_lifecycle/test_account_lifecycle.py` | The old account-lifecycle module | That module was deleted; export and deletion now live on `account/router.py` and are covered by `integration/account/test_account.py`. |
| `tests/architecture/test_router_hygiene.py` | Router line budgets and helper allow-lists | A style budget that the redesign's module split made meaningless. `unit/architecture/` keeps the three checks that guard a real invariant. |
| `tests/learning/{test_round_scheduler,test_session_read,test_session_recap,test_session_store_cas,test_apply_verdict,test_score_state_engine,test_planning_admission,test_submit_answer_pending,test_supply_task_submission,test_fsrs_idempotency_concurrency}.py`, `session_state.py` | The pre-redesign session machine, its CAS, and its own planning admission | Replaced by the Redis session document and the round store. The surviving properties moved to `integration/learning/`; FSRS arithmetic moved to `unit/learning/`. |
| `tests/hierarchy/test_hierarchy_integrity_migration.py`, `tests/test_embedded_cutover_deployment.py` | A one-off migration rehearsal and a Lexi cutover check | Deployment rehearsal is an operational gate, not a unit test. The live equivalent is `scripts/rehearse-fresh-schema.sh` plus `integration/test_baseline_migration.py`. |

## Retired in this phase

| Retired file | Why | Where its assertion lives now |
|---|---|---|
| `tests/assistant/test_confirmation_targets.py` | Asserted a metadata shape the server never sent | `unit/assistant/test_approval_interrupt.py` (the interrupt/resume payload shape) and web `tests/integration/assistant/approval-card.test.tsx` (rendering). |
| `tests/assistant/test_message_flow.py`, `test_threads_runs_and_actions.py` | Built on the `assistant_runs` table dropped by migration `0007` | `integration/assistant/{test_thread_lifecycle,test_run_usage_settlement}.py`. |
| `tests/assistant/test_event_read_contract.py`, `test_stream_recovery_and_retention.py` | Asserted the custom run-event store and a hand-rolled compactor | `unit/assistant/test_ag_ui_stream_contract.py` (the AG-UI wire contract) and `unit/assistant/test_boundaries.py`. |
| `tests/assistant/test_deferred_cache_invalidation.py` | The deferred-invalidation queue was removed | `integration/hierarchy/test_content_edit_fanout_is_constant.py` asserts the property directly: an edit touches one deck. |
| `tests/assistant/test_word_generation_tool_uses_durable_tasks.py` | Asserted a tool wired to the deleted DB task table | `system/test_content_jobs.py` proves the real path end to end. |
| `apps/web/tests/e2e/{golden-journey,assistant-ag-ui,product-journeys}.spec.ts`, `fixtures/product-journey.ts` | Minted Pycil HMAC session cookies and called `docker exec redis` to force a session's requested level. Both reach inside the product to make a screen pass, and the cookie-signing helper they call no longer exists. | Nothing yet — these are the coverage map for the browser-journey phase. The visible behaviour they asserted (nested folders, reload resuming, approval card, round break) is real and must be re-expressed through Clerk's test path and API seeding. |
| `scripts/{run-golden-journey,deterministic-openai-provider.py}`, `docker-compose.golden.yml` | A standalone product script and its Compose overlay. The provider is replaced by a test-owned fixture; the runner's cookie minting cannot work. | `tests/support/llm_gateway.py` (protocol-faithful, usage-reporting) and `tests/support/stack.py`. |

## Moved — unit level

Pure rules: no PostgreSQL, no Redis, no filesystem, no network. The suite runs with
the infrastructure unreachable, which is what proves the classification.

| From | To | Why this level |
|---|---|---|
| `tests/account/test_credit_periods.py` | `unit/account/` | Calendar-period arithmetic. |
| `tests/account/test_token_pricing.py` | `unit/account/` | Token-to-milli-credit conversion and the catalog's own shape. |
| `tests/assistant/test_ag_ui_agent_contract.py` | `unit/assistant/` | Prompt/state schemas. |
| `tests/assistant/test_ag_ui_stream_contract.py` | `unit/assistant/` | The AG-UI event sequence, checked through the SDK's own encoder. |
| `tests/assistant/test_approval_interrupt.py` | `unit/assistant/` | Interrupt and resume payload shapes. |
| `tests/assistant/test_attachments.py` | `unit/assistant/` | Image validation and historical-image stripping. |
| `tests/assistant/test_boundaries.py` | `unit/assistant/` | External-data boundary and stable prompt prefix. |
| `tests/assistant/test_configuration_and_tools.py` | `unit/assistant/` | Tool schemas and the 14-tool registry. |
| `tests/assistant/test_prompt_contract.py` | `unit/assistant/` | Rendered system prompt. |
| `tests/assistant/test_turn_usage_billing.py` | `unit/assistant/` | Turn cost arithmetic from reported usage. |
| `tests/auth/test_internal_secret.py` | `unit/auth/` | Secret comparison. |
| `tests/auth/test_production_configuration.py` | `unit/auth/` | Deploy-time placeholder refusal. |
| `tests/common/test_retry.py` | `unit/common/` | Backoff arithmetic. |
| `tests/content/test_embedded_lexi_construction.py` | `unit/content/` | One-reader-per-process composition, with the adapter patched. |
| `tests/content/test_lexi_contract_parity.py` | `unit/content/` | Static parity between Pycil's adapter and Lexi's contracts. |
| `tests/content/test_lexi_library.py` | `unit/content/` | Reader adapter behaviour. |
| `tests/hierarchy/test_single_cached_subtree_read.py` | `unit/hierarchy/` | A source-shape assertion: the fence lives in exactly one module. |
| `tests/learning/{test_delivery_payload_leak,test_depth_ladder,test_difficulty_sampler,test_history,test_resolver}.py` | `unit/learning/` | Delivery payload typing, depth ladder, sampling, history buckets, level fallback. |
| `tests/learning/fakes.py` | `support/lexi_fakes.py` | **Shared by both levels** — a fake used from a unit test and an integration test belongs in the shared floor, not in either level. |

## Moved — integration level

One module against real disposable PostgreSQL and Redis, or a rendered component
against controlled HTTP.

| From | To | Why this level |
|---|---|---|
| `tests/account/{test_account,test_credit_endpoint}.py` | `integration/account/` | Ledger transactions, uniqueness, the credit route. |
| `tests/auth/test_clerk_identity.py` | `integration/auth/` | JWKS verification and JIT mapping against a real database. |
| `tests/assistant/{test_disconnect_settlement,test_model_catalog_endpoint,test_run_usage_settlement,test_send_message_size_limit,test_thread_lifecycle,test_thread_ownership,test_turn_lease}.py` | `integration/assistant/` | Durable thread rows, lease CAS in Redis, settlement. |
| `tests/assistant/test_hierarchy_facade_listing.py` | `integration/assistant/` | The facade against real SQL. |
| `tests/content/{test_deck_membership,test_sense_detail,test_word_search_auth_boundary,test_deck_batch_membership}.py` | `integration/content/` | Deck membership constraints and the sense authorization matrix. |
| `tests/hierarchy/{test_cache_generation_interleavings,test_content_edit_fanout_is_constant,test_global_analytics,test_hierarchy_frontend_contract,test_idor,test_inherited_visibility_reference_revocation,test_node_path_and_counts,test_query_budget_list_nodes,test_readability_rule_parity,test_subtree_stats,test_tree_reference_cache_integrity}.py` | `integration/hierarchy/` | Recursive SQL, access rules, cache races, query budgets. |
| `tests/learning/{test_aborted_answer_recovery,test_answer_counters,test_answer_durability_and_crash_recovery,test_dashboard,test_rubric_grading_charge,test_session_flow,test_session_projection,test_session_resume_and_recap,test_session_store,test_user_learning_settings_effect}.py` | `integration/learning/` | The Redis session document and the per-answer transaction. |
| `tests/performance/test_hierarchy_query_budget.py` | `integration/performance/` | Loads large synthetic data; needs a database. Still opt-in. |
| `tests/{test_middleware_error_contract,test_readiness,test_unhandled_error_envelope,test_v1_contract}.py` | `integration/common/` | The ASGI app with its real middleware stack. |
| `tests/test_baseline_migration.py` | `integration/` | Runs Alembic against a disposable container. |

## Created in this phase

| File | Level | What it proves |
|---|---|---|
| `tests/support/stack.py` | support | A running API and worker over real stores, on ephemeral ports, stopping what it starts. |
| `tests/system/conftest.py` | system | One stack per session; the Clerk stub and LLM gateway the stack processes are pointed at. |
| `tests/system/test_stack_contract.py` | system | The scaffold itself: a real socket, a worker heartbeat that makes readiness pass, and a token verified against a JWKS document fetched over HTTP. |
| `tests/system/test_content_jobs.py` | system | The full job path: the API publishes, the **worker process** consumes, calls the provider, writes Lexi, and the API reads the receipt back. Plus receipt ownership. |
| `tests/support/llm_gateway.py` | support | Replaces the retired standalone provider. Reports usage and cache detail, honours schema constraints (`enum`, `anyOf`, `maxLength`) and the dictionary's own narrow fields. |
| `tests/integration/assistant/test_llm_gateway_fixture.py` | integration | Drives the real OpenAI-compatible client against the gateway, so a wrong wire shape fails here rather than in a later test. |
| `tests/unit/architecture/test_test_level_isolation.py` | unit | A level does not import a fixture from a level above it. |
| `apps/web/tests/integration/{setup.ts,server.ts}` | integration | jsdom plus MSW, with an undeclared request an error rather than a pass-through. |
| `apps/web/tests/integration/assistant/approval-card.test.tsx` | integration | The approval gate as rendered: the target is named, the destructive framing is on the approve control, nothing is decided without a click. |
| `apps/web/tests/integration/assistant/model-selector.test.tsx` | integration | The server's catalog drives the control; an unsupported effort is not carried across a model change. |
| `apps/web/tests/integration/study/session-runner.test.tsx` | integration | One `/next` per state that wants one, exposure has no submit control, a refusal is not shown as graded. |
| `apps/web/tests/integration/library/start-session-panel.test.tsx` | integration | Deck and folder copy differ; a session with no work says so instead of opening empty. |
| `apps/web/tests/integration/account/credit-and-export.test.tsx` | integration | The allowance clamps at zero and renders nothing while unknown; the export revokes its object URL. |

## Defects this classification surfaced

Moving a test to the level it actually belongs at is a claim about what it touches.
Three of those claims turned out to be false, and each was a real bug:

1. **`test_a_rotated_signing_key_is_accepted_after_a_cache_refresh`** was classified as
   integration but requested no database fixture, so it only passed because an autouse
   fixture started PostgreSQL for every test in the suite. It now requests `engine`
   explicitly. Removing that autouse fixture is also what makes the unit suite run in
   3 seconds without Docker instead of 24.
2. **The web job-status vocabulary was stale.** The API returns
   `queued/running/done/failed/expired`; the web polled for `success`/`error`. A
   finished job would have polled forever and rendered as "Working". The route returns
   a bare `dict`, so the generated contract could not catch it — it is now typed on
   the client from the server's own vocabulary.
3. **The activity store's ordering guard was built on `attempt`**, a field no receipt
   carries. Ordering is now by status, which is the property the guard actually needs.

## Unresolved

- The browser journeys are not yet re-expressed. Phase 14 owns them; the retired specs
  are the coverage map, not a substitute.
- `tests/integration/performance/test_hierarchy_query_budget.py` stays opt-in behind
  `RUN_HIERARCHY_PERFORMANCE=1` and is therefore not part of any default level run.
