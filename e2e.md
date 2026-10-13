# Root E2E Testing Redesign

Status: implementation in progress. The independent package and real-stack pilot
exist; full journey coverage, failure-path proof, and legacy cutover are pending.

This document expands the proposed root-level E2E design using another source
scout. It records the intended architecture, test ownership, journeys, rollout,
verification, and deletion work. It is an execution record, not evidence that the
new suite already exists or passes.

## 1. Outcome, constraints, and completion criteria

### Outcome

Create one product E2E package at `e2e/`. It must verify real user journeys through
the production Next.js frontend, Clerk development identity, the Pycil HTTP API,
PostgreSQL, Redis, Tantivy, native model clients, and Assistant checkpoints.

Ordinary E2E controls only the external model boundary. A separately selected live
suite uses actual model and decision providers. Both use disposable application
infrastructure and real identity sessions.

### Constraints

- Preserve the accepted frontend architecture: server-rendered initial content;
  browser interactions call Pycil directly after hydration. Do not introduce a
  Next.js CRUD/filter/pagination proxy to make testing easier.
- Preserve existing product contracts. Fix genuine defects exposed by tests at
  their production owner; do not add test-mode branches to business code.
- Use Ponytail principles throughout implementation: small explicit helpers,
  existing application behavior, meaningful checks, and no unnecessary framework.
- Rewrite around business behavior after reading source. Do not mechanically move
  the existing suite or copy its implementation assumptions into new helpers.
- Preserve valuable regressions, validation, authorization, error handling, and
  accessibility. Delete duplication only after identifying its surviving owner.
- Keep browser integration in `apps/web/tests`; backend unit/integration tests
  stay in `apps/api/tests`. Do not delete or rebuild those entire suites.
- No backward compatibility aliases, retired runner, dead fixtures, permanently
  skipped placeholders, or two E2E entry points after cutover.
- New string enum values, when needed, use `snake_case`; do not perpetuate uppercase
  string values or duplicate product enum definitions unnecessarily.
- No secrets, auth states, reports, database exports, or personal data in Git.
- Cleanup targets only resources owned by the current run. Never flush a shared
  Redis instance, touch a development database, or terminate an unrelated server.

### Non-goals

No backend system/performance suite, custom test framework, broad page-object
hierarchy, billing implementation, S3/TTS pipeline, new observability platform,
or production deployment rehearsal. Do not invent tests for removed features such
as Stars/Pins/tags/import/audio. Existing learning-language preferences are settings;
they do not imply an independently exposed translation workflow.

### Completion criteria

1. Root package commands run the documented default/live/mobile/external-auth
   scopes without delegating to the old Python runner.
2. The actual API image, explicit migration gate, reference import, native
   checkpoint schema, and search readiness are exercised.
3. Mutation journeys run independently with two workers and fresh test actors.
   A failed test cannot poison the next actor or provider scenario.
4. Every journey listed below is implemented, or deliberately assigned to an
   existing lower-level owner with evidence. Missing coverage is not reported as
   success. Optional external-auth prerequisites are reported separately.
5. No-JavaScript assertions prove visible initial domain content; hydration and
   subsequent interactions prove the accepted data-fetching boundary.
6. Setup, test, provider, and cleanup failures are distinguishable and retained
   privately. Live failures remain failures even if a later independent run passes.
7. Old E2E code/config/scripts/dependencies and stale operational instructions are
   removed. Each test is collected by exactly one intended suite/project per
   selected execution profile.

## 2. Source scout and business boundaries

Source was inspected with CodeGraph first, followed by targeted reads of current
files, test registration, fixtures, Docker configuration, and CI. Some historical
documentation still describes retired routing; current source takes precedence.

### Current implementation evidence

| Area | Source anchors | Contract that determines E2E design |
| --- | --- | --- |
| Identity | [account auth](apps/api/pycil/account/auth.py), [lifecycle](apps/api/pycil/account/lifecycle.py), [auth UI](apps/web/src/features/auth/clerk-form.client.tsx) | JWT identity is verified; missing accounts are checked with Clerk before provisioning; roots are provisioned through the real account path. Actor context is cached in Redis. |
| Account | [account module](apps/api/pycil/account/), [policy](config/config.yaml) | Sparse settings updates preserve unrelated fields. Public profiles exclude private settings/usage. Plan changes are not a public purchase API. |
| Library/publication | [library module](apps/api/pycil/library/), [public actions](apps/web/src/features/library/public-collection-actions.client.tsx) | Physical ancestry and active roots determine access. Publication is a move with consent. Copies are independent; references resolve live targets. Signed-in users can study public content directly without saving it. |
| Vocabulary | [generation tasks](apps/api/pycil/vocabulary/generation/jobs.py), [reference module](apps/api/pycil/vocabulary/references/) | Reference data is immutable source evidence, not already generated content. Generation is process-owned singleflight, publishes real Word/Sense data, and updates Tantivy. Status is not a durable job record. |
| Study | [routes](apps/api/pycil/study/api.py), [grading](apps/api/pycil/study/grading.py), [models](apps/api/pycil/study/models.py), [capabilities](apps/api/pycil/study/enums.py) | Eight public question types, six artifact kinds, three response formats. Prepare/grade do not write learning progress. Submit requires an idempotency key; progress belongs to user–sense, not deck membership. |
| Assistant | [routes](apps/api/pycil/assistant/api.py), [graph](apps/api/pycil/assistant/graph.py), [stream](apps/api/pycil/assistant/stream.py) | Real AG-UI SSE, native tools, Postgres checkpoints, Redis turn leases, approval interrupts, and usage settlement. Tool writes use the same authorization/services as HTTP routes. |
| Model boundaries | [LLM clients](apps/api/pycil/infrastructure/llm.py) | Structured generation uses Instructor over Chat Completions; grading uses the native Decisions protocol; Assistant uses streaming OpenRouter-compatible chat and tool calls. One fake generic JSON endpoint is insufficient. |
| Startup | [resources](apps/api/pycil/app/resources.py), [schema verification](apps/api/pycil/infrastructure/database.py), [migration CLI](apps/api/pycil/app/migrate.py), [API image](apps/api/Dockerfile) | API startup verifies schema/reference data, opens native checkpoint resources, then initializes real search. It does not migrate automatically. |
| Rendering | [server services](apps/web/src/lib/api/services/server.ts), [API configuration](apps/web/src/lib/api/services/config.ts), [auth completion](apps/web/src/app/(auth)/auth/complete/route.ts) | Server services use Clerk server auth. Server and browser API origins have separate configuration. Auth completion is a legitimate Next route that reads account locale and sets a cookie. |
| Existing test ownership | [backend testing](docs/backend/testing.md), [web testing](apps/web/tests/README.md), [CI](.github/workflows/test.yml) | Backend integration already owns many tree/scoring/transaction/checkpoint invariants. Frontend browser integration controls HTTP/UI boundaries. Current full-stack E2E ownership is still under `apps/web`. |

### Business invariants to protect through the browser

| Domain | Required end-to-end behavior |
| --- | --- |
| Account | One Clerk identity produces one Pycil account/root set; settings/profile persist; another session or account never inherits private cached data. |
| Library | Folder, deck, and reference behaviors remain distinct; copy independence and reference liveness are observable through the UI. |
| Published/Discovery | Consent precedes publication; guest reads follow current access; unpublish/delete revokes reads and subscriber reference access. |
| Vocabulary | Unprepared reference versus Ready word is visible; generation produces readable native content and searchable results. |
| Study | Browser session recovery survives relevant failures; preparation/grading are read-only; submission records results once. |
| Progress/Home | The same sense across decks/references is counted once for an actor; reviewing it affects all relevant scopes and respects activity timezone semantics. |
| Assistant | Incremental streaming, checkpoint reopen, pending approval, authorized writes, cancellation, and usage settlement reach real services. |
| Rendering/navigation | Request-specific server content is visible initially; browser actions use direct Pycil requests; URL/history and session changes remain coherent. |

Do not turn E2E into a second exhaustive backend suite. Exact scoring formulas,
closure maintenance, lock behavior, cursor validation, and batch atomicity have
lower-level owners; E2E proves the user-facing journey across these boundaries.

## 3. Problems in the current E2E design

These are concrete ownership/isolation/coupling problems. Python setup, a frontend
directory, or `workers: 1` is not inherently nonstandard.

| Finding | Evidence | Replacement |
| --- | --- | --- |
| Runner owns too many lifecycles | [run.py](apps/web/tests/e2e/run.py) parses several dotenv sources, creates Clerk users, starts containers/processes, polls readiness, copies the web source/dependencies, builds Next, invokes Playwright, and copies reports. | Playwright owns web/test execution; Testcontainers owns the Compose stack; fixtures own actors/data; seed owns only backend state preparation. |
| Shared mutable actor state | Runner creates A/B/C once. Tests modify their settings, progress, conversations, and usage. [fixtures](apps/web/tests/e2e/fixtures.ts) deletes tracked nodes but cannot restore all account state. | Fresh test-scoped actors for mutation journeys; no settings-restoration contract between unrelated tests. |
| Test execution order masks interference | [Playwright config](apps/web/playwright.config.ts) has one worker and no full parallelism. | Independent actors and provider scenarios; verify two-worker execution before increasing concurrency. |
| Quiz automation uses its own implementation as an oracle | [study helper](apps/web/tests/e2e/helpers/study.ts) imports `StudySession`, reads phase/position/localStorage, and selects the stored correct option. [question tests](apps/web/tests/e2e/study-questions.test.ts) import `currentQuestion`. | Visible prompt/option matching against independent expected answers. Storage access only for storage-specific recovery cases. |
| Artificial lexical duplicates | [seed data](apps/web/tests/e2e/support/data.py) uses many financially identical `bank` senses and over a page of duplicate `archive` senses with magic IDs. | Distinct meaningful fixture items, semantic manifest keys, and explicitly reserved cold/generated resources. |
| Global provider failure state | [provider](apps/web/tests/e2e/support/provider.py) uses a shared Counter for initial refusals and command-like `E2E ...` messages. Decisions can fall back to the first available choice. | Registered test-owned response sequences and exact matching. No unmatched-request success response or guessed decision choice. |
| API invariant tests presented as browser journeys | [library management](apps/web/tests/e2e/library-management.test.ts) sends concurrent mutations, invalid batches, cycle attempts, and protected-root writes mostly through helpers. | Assign invariants to backend integration; retain UI cancellation/error/authorization outcomes at E2E. |
| Runtime imports create circular verification | Tests import application URL helpers, parsers, and session logic. | Independent HTTP client and small E2E DTOs; public HTTP/UI behavior is the assertion surface. |
| Live scope is ambiguous | `llm-provider.test.ts` mixes UI and API-only checks; `E2E_GREP` often selects only part of it. | Three fixed live journey files and an explicit command/report. Focused developer selection remains possible but cannot be called a full live pass. |
| Reports/config lifetimes overlap | Browser integration and E2E share one Playwright config. A previous report-directory cleanup removed a running E2E setup log. Output directories were separated as an immediate fix. | Separate package, config, output roots, and collection. |
| Context tracking patches a library object | [browser-errors helper](apps/web/tests/e2e/helpers/browser-errors.ts) replaces `browser.newContext`. | Fixtures create and instrument their owned contexts directly; restore listeners in their own teardown. |
| CI cannot express all coverage distinctly | Current live input replaces default E2E, and full-stack work runs as a frontend-owned job. | Product E2E jobs with explicit default/live status; live adds evidence rather than replacing default coverage. |

Existing useful assertions must survive: publication revocation, logical scope
deduplication, native approval persistence, accepted-write/lost-response behavior,
graded-answer recovery, flashcard page restoration, and visible SSR content.

## 4. Stack and ownership decisions

| Responsibility | Selected technology/owner | Reason |
| --- | --- | --- |
| Browser runner, assertions, HTTP requests, reports | Playwright Test | Existing runner; built-in contexts, fixtures, request client, webServer, and diagnostics. |
| E2E/setup/support code | TypeScript in a standalone root Node package | Browser suite has one language and independent tooling ownership. |
| Disposable backend topology | Testcontainers Node.js Compose support | Standard container readiness and run-owned cleanup; reuse actual API image. |
| Production frontend lifecycle | Playwright `webServer`, `next build` + `next start` | No handwritten process supervisor/readiness polling or source snapshot copying. |
| Identity setup | `@clerk/testing` + Clerk Backend SDK | Real sessions with official setup helpers; real custom auth UI tested separately. |
| Migration/reference import | `python -m pycil.app.migrate --reference ...` in API image | Exercises the real baseline, native checkpoint setup, and validated JSONL importer. |
| State unavailable through public APIs | One finite `support/seed.py` | Uses backend models and validation; no persistent seed server or test-only production endpoints. |
| Controlled model service | `support/model-provider.ts` using Node HTTP/SSE | Small external-boundary adapter; no extra web framework or provider simulation framework. |
| CI | GitHub Actions | Same package commands and container/image paths as local runs. |

Use the repository's Node/pnpm versions and lock resolved compatible dependency
versions. Keep one Playwright version per package; do not add a second direct
`playwright: latest` dependency when `@playwright/test` provides everything needed.
Keep Playwright in the web package for its browser integration tests.

Use a standalone `e2e/package.json` and lockfile. Do not introduce a root workspace
or reorganize application package management as an incidental testing change.
Do not add Faker, BasePage, a generic repository layer, tsx, or a second assertion
runner without a concrete need. The controlled provider should be executable with
the chosen Node runtime's supported TypeScript subset and built-in modules.

### Tooling guidance, not a claim of a universal standard

Playwright documents server lifecycle, isolation, fixtures, and authenticated
state. Testcontainers documents Compose health checks and disposal. These support
the design, but neither mandates this exact folder tree or business file list.
Test-scoped actors are this project's choice because its mutation state is broad;
they are stricter than Playwright's documented account-per-worker alternative.

## 5. Folder structure and file responsibilities

```text
e2e/
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── playwright.config.ts
├── global-setup.ts
├── README.md
├── fixtures/
│   ├── index.ts
│   ├── actors.ts
│   ├── data.ts
│   └── provider.ts
├── support/
│   ├── environment.ts
│   ├── stack.ts
│   ├── compose.yaml
│   ├── seed.py
│   ├── api.ts
│   ├── study.ts
│   ├── assistant.ts
│   ├── model-provider.ts
│   └── data/
│       ├── reference.jsonl
│       ├── vocabulary.json
│       ├── questions.json
│       └── provider-scenarios.json
├── tests/
│   ├── public/
│   ├── auth/
│   ├── account/
│   ├── home/
│   ├── library/
│   ├── discovery/
│   ├── vocabulary/
│   ├── study/
│   ├── assistant/
│   ├── platform/
│   ├── live/
│   └── external-auth/
└── .artifacts/                 # ignored run-owned output, never source fixtures
```

| File | Responsibilities and boundaries |
| --- | --- |
| `playwright.config.ts` | Explicit project selection, ports/origins, timeouts, two workers, collection, private reporters, production webServer, graceful shutdown. Validate required inputs before starting anything. |
| `global-setup.ts` | Clerk testing setup, stack startup, baseline manifest, serializable worker runtime metadata, and returned teardown closure. Catch partial setup failure and clean owned resources. No business assertions here. |
| `fixtures/index.ts` | Compose fixture dependencies, expose `test`/`expect`, and instrument test-owned pages/contexts. No monkey-patching. |
| `fixtures/actors.ts` | Fresh Clerk identities, session setup, real provisioning, guest/secondary contexts, cleanup ledger, session revocation operations for auth tests. Additional contexts are lazy. |
| `fixtures/data.ts` | Real API setup for nodes/membership/publication and named preparatory seed requests for plan/usage/due state. Track owned resources for teardown. |
| `fixtures/provider.ts` | Register, verify consumption of, and remove test-owned provider scenarios. Live mode must not accidentally register a controlled scenario. |
| `support/environment.ts` | Finite input validation and one run ID; derives deterministic endpoints/build/output paths. No automatic application dotenv discovery. Runtime manifest carries handles/IDs, never secrets. |
| `support/stack.ts` | Compose startup/readiness, owned container handles, finite seed invocation, sanitized diagnostics, explicit down with volume removal. Does not become a replacement test runner. |
| `support/compose.yaml` | Disposable PostgreSQL/Redis/API and controlled-provider profile; migration/seed startup dependency. No production volume names, fixed container names, Caddy, or unrelated services. |
| `support/seed.py` | Baseline lexical/question import and a small list of actor preparation operations. Validate input, operate transactionally, close resources, output a semantic ID manifest. Never launch servers or Playwright. |
| `support/api.ts` | Playwright APIRequestContext authenticated with an actual session token, refreshed before requests as needed. Explicit expected status and independently defined DTOs. No frontend transport/parser import. |
| `support/study.ts` | Small repeated UI operations: start, select/type an expected answer, continue, pause, finish. No general session-store reader or exported grading implementation. |
| `support/assistant.ts` | Open panel, send messages, choose conversation, approve/reject, wait for user-visible state and actual run termination where necessary. |
| `support/model-provider.ts` | The external protocols, bounded request validation, independently keyed scenarios, incremental SSE, deliberate errors/refusals, completion/consumption diagnostics. No Pycil business logic. |
| `support/data/*` | Compact reviewed reference, lexical and question fixtures; plain provider input/output examples. No executable custom DSL or arbitrary templating engine. |
| `README.md` | Current commands, prerequisites, profiles, boundaries, cleanup recovery, artifact privacy, and troubleshooting; link to this design rather than copying it. |

Helpers contain actions or preparation. Assertions about a journey remain readable
in its test file. Split a file only when it has genuinely different responsibilities;
do not create a class for each screen or a configurable general workflow engine.

## 6. Lifecycle, networking, and build isolation

### Startup order

The installed Playwright runner currently executes plugin setup (including
webServer) before `globalSetup`. This was verified in
`apps/web/node_modules/.pnpm/playwright@1.64.0/node_modules/playwright/lib/runner/index.js`,
at `createGlobalSetupTasks`. It is implementation evidence for the installed
version, not a permanent undocumented contract to assume after upgrades.

Use the following sequence and prove it with the initial lifecycle experiment:

1. Resolve/validate explicit inputs and derive a run ID in configuration. Reading
   config may derive paths; importing config must not start containers or create
   remote users. Use separate artifact roots for browser output and setup metadata,
   because Playwright cleans its configured output directory.
2. Playwright webServer builds and starts Next in production mode with the fixed
   browser API origin. Readiness uses `/icon.svg`, not Home or another route that
   needs an account/API response. No test navigation occurs yet.
3. `globalSetup` configures Clerk test helpers and starts the owned backend Compose
   stack. PostgreSQL/Redis become healthy, then the real migration/reference gate
   and baseline seed complete, then the API starts and becomes `/ready` healthy.
4. Default profile starts the controlled provider before API readiness. Live
   profile uses only the explicit external provider addresses/credentials.
5. Publish the minimal worker runtime manifest and baseline semantic IDs. Keep
   Testcontainers/Compose handles alive in the main setup lifetime.
6. Fixtures register scenarios and create/provision actors/data only when requested.
   All tests start after stack and web readiness.
7. Test teardown first finishes/cancels owned work, removes scenario registrations,
   deletes owned nodes/conversations while identity is valid, closes contexts and
   request clients, then deletes owned Clerk identities. Each cleanup step still
   runs if an earlier step fails.
8. Global teardown reconciles the identity ledger, saves private diagnostics,
   removes the Compose project/volumes/networks, and reports failures. Playwright
   stops its webServer process. Global teardown must not assume that webServer has
   already stopped and delete files from its active build directory.

Global setup can return a teardown function; this is the container-lifetime owner.
Do not keep stack ownership in a setup-project worker that exits before dependent
tests and inadvertently ends its Testcontainers reaper session. Project dependencies
are useful for reportable test setup, but do not solve this particular lifetime
problem automatically.

Setup failure must preserve the original cause and collect cleanup failures too.
Do not rely on the normal returned teardown to clean a setup that never returned.
Keep Testcontainers automatic cleanup enabled; it does not delete Clerk users.
Abrupt host death may still require the documented owned-identity recovery command.

### Network contract

| Consumer | Address/topology |
| --- | --- |
| Browser/frontend | `http://localhost:3200` |
| Browser direct Pycil requests | `http://127.0.0.1:8100/v1/...` |
| Host Next server fetches | `PYCIL_API_URL=http://127.0.0.1:8100`; frontend configuration adds `/v1`. |
| Browser build-time configuration | `NEXT_PUBLIC_PYCIL_API_URL=http://127.0.0.1:8100`, `NEXT_PUBLIC_DATA_MODE=live`. |
| API PostgreSQL/Redis | Compose service DNS, not host loopback. PostgreSQL URL uses `postgresql+asyncpg`. |
| API controlled models | Compose provider DNS for Chat Completions and native Decisions endpoint. Host control interface, if needed, is loopback-bound on the reserved provider port. |
| CORS | Exactly the actual frontend origin, including hostname and port; `localhost` and `127.0.0.1` are not interchangeable origins. |

Reserve the documented frontend/API/provider ports; occupied ports fail instead
of silently incrementing or reusing another process. Keep development ports
3000/8000 and browser integration port 3100 untouched. Internal database ports
need not be exposed to the host when setup executes inside the API image.

Use a unique Compose project name, no globally fixed `container_name`, no reusable
application volumes, and read-only fixture mounts. Docker readiness checks must
use tools available in the actual image; do not assume curl is installed. Verify
one-shot migration/seed success with an appropriate exit-code wait, not a
listening-port wait. API `/ready` must reflect schema, stores, and real search.

### Remove snapshot copying without colliding with development

- Add a narrowly scoped build-directory override to the current Next configuration
  if needed: ordinary commands keep `.next`; E2E uses a run-specific directory
  inside `apps/web`, for example `.next-e2e/<run-id>`.
- Next's supported `distDir` must remain inside the web project. Do not point it
  at `../../e2e/.artifacts` or copy the whole application/node_modules tree.
- Supply the same distDir and environment to `next build` and `next start` through
  Playwright webServer. Set a build-appropriate startup timeout and graceful
  shutdown; no second supervisor script.
- Treat ignored build output as a build cache, distinct from browser diagnostics.
  Provide a finite explicit cleanup command that removes only recorded completed
  run directories after checking no owned web process is active. Do not add a
  process runner just to delete a build cache. Failed-run diagnostics remain until
  their documented retention/explicit cleanup, rather than being erased on failure.
- Explicit environment overrides define all application-owned API/Clerk/model
  settings needed for the run. Next has its own standard dotenv loading; removing
  the runner's dotenv scan does not disable Next's built-in behavior. Do not
  claim otherwise, and do not use nonstandard NODE_ENV values to work around it.
- Prove production build/static readiness does not require a live backend before
  global setup. If source changes invalidate that fact, revise the lifecycle from
  concrete evidence before implementing the remaining suite; never feed mock
  business responses into a supposed production build to conceal the dependency.

## 7. Actor, fixture, and database isolation

### Fresh actors

- Use test-scoped actors for mutation journeys. A primary actor, optional second
  actor, and optional guest context are independent; use no global A/B/C accounts.
- Generate owned identity addresses under the Clerk test-address convention with
  run/test uniqueness. Register the exact email before signup or SDK creation;
  record the returned user ID immediately afterward.
- Use Clerk development credentials only. Verify secret/public key/issuer belong
  to the same configured test instance. Fail early on missing or production keys;
  print variable names, never secret values.
- Ordinary business fixtures use the official Clerk sign-in helper, then follow
  the application auth-completion/provisioning path as needed. The helper creates
  a real session but can bypass verification; it does not verify the custom login
  form. Dedicated auth tests exercise that form without replacing the target flow.
- Build public HTTP clients from actual session tokens, not handwritten JWTs or
  an email claim. Refresh tokens when required by a long-running test.
- No-JS contexts may receive test-owned authenticated cookie state from setup;
  they must actually render authenticated server content, not only serialized data.
- Browser error tracking attaches directly to every fixture-created context/page,
  including popups and secondary actors. Unexpected page exceptions fail the
  owning test; console/network diagnostics are classified, not broadly ignored.

### Provisioning and finite actor preparation

Do not preinsert users or roots. The actor must first call the actual authenticated
account route so real provisioning happens. Tests can then request the few states
that cannot be arranged through a public API:

- Pro plan;
- exhausted current allowance;
- overdue/not-yet-due memory for named senses;
- narrowly reserved artifact state for an intentional stale-artifact recovery test.

Run `seed.py` inside the exact run-owned API container, using a finite command/input
schema and bounded execution. Baseline can use Testcontainers container execution;
worker fixtures may use a bounded native `docker exec` invocation with argument
arrays and the validated owned container ID. This is a seed command, not a new
subprocess supervisor. Never expose Docker/socket access through the production API.

The seed program verifies the fixture/run identity before altering actor state,
uses a transaction, validates models/artifacts, and returns only safe IDs. Do not
create a generic SQL executor, arbitrary table updater, or seed HTTP service.

**Cache consistency is required.** Provisioning caches ActorContext in Redis.
Updating plan after provisioning must invalidate only that actor's cached context
through the application invalidation convention and correct runtime namespace.
Do not flush Redis, wait for TTL, recreate the cache with a guessed namespace, or
call the full application resource lifespan just to seed one actor. After preparation,
verify the public account response exposes the intended effective state before Act.

Seed immutable baseline lexical/question data before API search initialization.
Do not insert new words directly into SQL after startup and assume Tantivy noticed.
Runtime generation uses the genuine API/search update path. Actor memory updates
do not require lexical reindexing.

### Resource cleanup and shared public listings

Each fixture owns a small resource ledger. Delete owned nodes/conversations while
the actor is authenticated; remove published data so unrelated Discovery tests do
not encounter abandoned content. Close clients and contexts even if deletion fails.
Treat already removed owned resources as successfully absent, not an excuse to
ignore every unexpected status.

Application user rows can remain inside the disposable run database until the stack
is destroyed; there is no invented production delete-account endpoint. Fresh actor
IDs prevent reuse. Discovery assertions scope to the test's unique owner/resource,
not the total public catalog size. Final identity reconciliation uses exact ledger
entries, never every user whose email contains a vague test prefix.

## 8. Baseline data and question automation

### Lexical fixtures

Use a small reviewed set of real meanings with different observable roles:

- `bankFinancial` and `bankRiver` distinguish senses of the same word;
- a verb with real inflections and related navigation;
- an expression with an actual pattern/slot where the UI supports it;
- named new, overdue, and not-yet-due learning resources;
- reserved cold artifact resources and reserved generation targets.

Preserve immutable source Reference IDs in the JSONL subset. Runtime Word/Sense,
artifact, and node IDs come from a semantic manifest; tests never assume
`sense_ids: [18]` means a particular fixture. Definitions/examples/POS/form fields
must agree. Do not reuse one bank answer generator for unrelated meanings.

Pagination fixtures must exceed the actual page boundary with distinguishable,
valid items. Generate a bounded reviewed dataset from meaningful inputs; do not
pad it with 133 semantically identical senses merely to reach page two. Keep the
normal baseline compact and isolate larger pagination fixtures from ordinary
collection assumptions. Vocabulary can be globally shared as read-only baseline;
learning state is actor-specific.

The reference subset is a committed, validated E2E fixture with provenance, not
extracted from the full Git LFS artifact on every test run. Existing production
reference validation remains a separate owner. Root E2E should not need the entire
reference dataset merely to test a handful of words.

### Independent answers

- `questions.json` contains valid persisted artifacts and independently reviewed
  expectations keyed by visible prompt/semantic case, not private session shape.
- Seed uses real artifact validation/persistence conventions. Runtime preparation
  still uses the real prepare route and randomized question construction.
- Match an option by visible expected content, never its array position or the
  returned `question.correct` field. Type independently expected text for typed
  questions. If random variants exist, match the visible variant to the finite
  fixture expectations.
- Question order is not a global assumption. For a specific type/format, configure
  that actor's learning preferences through the real settings API or UI.
- A bounded UI completion helper may repeat answer/feedback/round actions, but it
  must fail on an unknown prompt or unsupported visible state. It must not silently
  skip questions or reimplement the session reducer/scoring.
- Reading/corrupting localStorage is explicitly allowed only in recovery tests
  whose subject is persistence, malformed storage, frozen replay, or competing
  tabs. Even those tests assert the user-visible outcome and real public persistence.

### Shared vocabulary mutations

Fresh actors do not isolate generated words or artifact caches. Each mutable cold
bank/generation/failure scenario gets a reserved target distinct from other tests
running in the same profile. Parameterized/mobile/browser executions require
separate reservations too. Never mutate or delete a shared baseline artifact used
by another test.

A retry/reuse test may intentionally reuse its own target. A separate generation
test may not pass because a previous test already generated that target. Assert
the target was not Ready before Act and that the intended provider path was used.
Do not delete global content between concurrent tests to reset this assumption.

## 9. Controlled provider contracts

### Preserve native application behavior

Default E2E keeps Instructor validation/reask, native Decisions parsing, real
Assistant graph/tool execution, SQL transactions, Redis coordination, checkpoints,
and Tantivy publication. Only HTTP responses from external model services are
controlled. Never intercept Pycil business routes and return fabricated successful
responses while describing the result as full-stack E2E.

The provider must implement the actual consumed wire surfaces:

1. Chat Completions structured-output responses/refusals for inventory, enrichment,
   and cold question-artifact generation.
2. Native Decisions request/answer format, including dynamic choice identifiers.
   Require an explicitly configured available choice; never choose the first
   criterion as a success fallback.
3. Incremental chat SSE with content/reasoning/tool-call fragments and meaningful
   usage, followed by the protocol termination required by the actual client.
4. Deliberate provider HTTP failures, refusal/invalid-output sequences, cancellation,
   and streamed errors needed by recovery journeys.

Do not invent a full LLM emulator. The provider produces registered deterministic
external responses; real Pycil executes the tools and persistence.

### Scenario matching and lifetime

- Register each test's response sequence before the target action; include finite
  expected call types and matching fields from real requests.
- For structured requests, match reserved lexical/reference/meaning inputs; for
  Decisions, match the real state/criteria; for Assistant, use the test's unique
  natural resource names, IDs, and conversation input/tool chain.
- Requests do not necessarily include actor ID. Do not assume a per-actor matcher
  can distinguish two identical shared lexical calls. Use reserved resources or
  equivalent stateless registered responses with an unambiguous owner.
- Do not add an application test-only correlation header, magic production prompt
  branch, or old `E2E create ...` instruction parser to obtain isolation.
- A scenario owns its counters, queues, stream gate, and deliberately failed first
  response. No suite-global failure Counter, defaults that hide unknown traffic,
  or request-order dependence across tests.
- Unknown/ambiguous requests fail with safe protocol/request-kind diagnostics;
  they never return a generic successful greeting. Assert required calls were
  consumed and unexpected calls did not occur. Allow only the explicitly bounded
  application retry/reask paths for the scenario.
- Stream tests use a controlled gate: verify partial text/reasoning is visible
  while the stream is still open, then release completion. No arbitrary long sleeps.
- Teardown waits for completion/cancellation of this test's provider work before
  removing its scenario. Unfinished work is a failure, not silently handed to the
  next test.
- Control endpoints are test-only, bounded, and available only on the disposable
  network/host loopback. Do not mount raw credential directories into the service.

Provider protocol/matching/cleanup and seed validation are nontrivial support logic.
Add small meaningful checks at their owner (or assert-based self-checks) rather
than creating directory/name/coverage tests. Verify valid output reaches the real
application, not only that the adapter can parse its own fixture.

## 10. Test inventory

Paths below are relative to `e2e/tests`. Each numbered behavior becomes a focused
case or a small related parameterized group. A file is a journey owner, not one
giant test containing every listed assertion.

### 10.1 Public, authentication, account, and Home

| File | Cases and assertions |
| --- | --- |
| `public/landing.test.ts` | Guest-visible landing and login/signup navigation; unknown route recovery; public content does not require an account response. Check usable links/headings rather than a screenshot existing. |
| `auth/sign-up.test.ts` | Real custom signup, incorrect verification code, resend, successful verification, safe return destination; repeated authenticated reads expose the same account and exactly one root set. Ledger the email before UI creation. |
| `auth/sign-in.test.ts` | Wrong credentials and recoverable error; login/logout/protected route; authenticated auth-page redirect; reload/new tab/token refresh; switching accounts removes prior private data; unsafe return destination is rejected; revoke an owned session and assert sign-in recovery. |
| `auth/password-reset.test.ts` | Reset request, wrong/correct verification, replacement password, login with new password, rejection of old password. Do not use the fast helper to bypass the flow under test. |
| `account/profile.test.ts` | Save display name/handle/bio and reload; public lookup and private-field exclusion; duplicate/invalid handle retains draft/saved profile; rename invalidates old handle lookup; clear bio to null; SSR draft remains editable during delayed Clerk readiness while saving waits for auth. |
| `account/preferences.test.ts` | Save locale/timezone/learning preferences, reload/another session, preserve unrelated fields, validate invalid drafts, retain draft on failed save/retry; Free versus Pro format restrictions; stored intent/effective behavior after fixture-prepared plan change. |
| `home/dashboard.test.ts` | Empty account; Home study action goes directly to correct scope; native prepare/grade do not change summary; completed submission changes counts/activity/schedule; overlapping scopes deduplicate; timezone changes and stable historical activity; real API outage/retry has no preview-data fallback. |

Authentication setup helpers and bot-protection test tokens are acceptable. They do
not replace application verification/sign-in assertions. Clerk/Google internal
implementation is not a second product under test.

### 10.2 Library, public discovery, and vocabulary

| File | Cases and assertions |
| --- | --- |
| `library/editing.test.ts` | Create folder/deck via UI, choose/add/remove meanings, metadata edit, nested placement, move/copy; copy IDs/memberships remain independent; delete cancel then subtree deletion and navigation recovery; failed edit retains draft; double click issues one write; accepted creation with lost response remains one persisted creation and a recoverable UI, without inventing a create replay contract. |
| `library/browsing.test.ts` | Nested breadcrumbs; folder and meaning pagination; search/sort/state filters on actual data; source provenance/overflow presentation; reload and Back/Forward; delayed older native response cannot overwrite latest results. |
| `library/publication.test.ts` | Cancel consent leaves private subtree unchanged; confirmed publication moves subtree; retained Personal reference works; guest can read; unpublish/delete revokes guest reads and subscriber content; owner can still navigate appropriately. |
| `library/references.test.ts` | Create reference via UI, observe source membership changes, distinguish from copy, deduplicate overlaps in scope/progress; broken/revoked target displays unavailable; do not duplicate exhaustive cycle/closure calculations here. |
| `discovery/public-library.test.ts` | Browse/search Published with owner/type filters and pagination; public profile/collection route; guest/other actor cannot edit private resources; Save to Personal creates a real reference; signed-in direct study of public content works without adding a Personal node. |
| `vocabulary/dictionary.test.ts` | Guest reads public dictionary while private context requires auth; Ready versus unprepared reference; POS/multiple senses/aliases/inflections/details/related navigation; multi-sense selection survives searches; add to existing deck or create nested deck; batched reads support the user outcome without coupling assertions to frontend parsers. |
| `vocabulary/generation.test.ts` | UI generation request, pending state, readable validated content/examples, search update, cold artifacts when learning the new word; controlled failure then explicit retry; existing content reuse; generation does not write learning progress. Reserve targets and assert intended provider consumption. |

### 10.3 Study

| File | Cases and assertions |
| --- | --- |
| `study/session.test.ts` | New/Due/Auto selects the intended fixture scope; answer/feedback/round recap/completion; submit updates progress; same sense in another deck/reference exposes the same user memory; practice retry preserves initial evidence and bounded attempts. |
| `study/question-types.test.ts` | User-visible operation for all eight public types; single-choice behavior never calls typed grade; legal single-word and short-answer UI branches use real grading; dialogue and sentence-rewrite render their distinct context; correct/wrong/don't-know and diagnostics. Parameterize representative legal pairs without duplicating the entire backend capability/rubric matrix. |
| `study/recovery.test.ts` | Cold-artifact refusal/retry; empty/missing scope; leave delayed prepare without creating/submitting a session; reload/pause/resume/early finish; separate-node sessions; competing-tab conflict; blocked/corrupted storage; stale grade request, retained/locked answer across lost grading response; prepare/grade/submit recovery; accepted submit with lost response replays the same frozen batch/idempotency key and does not duplicate progress/activity. |
| `study/flashcards.test.ts` | Reveal and next/previous, genuine page-two boundary, reload restores position beyond the first page, empty/unavailable scope; browsing emits no grade/submit and does not alter progress. |

The eight types are `definition_to_word`, `context_to_word`, `cloze_to_word`,
`word_to_definition`, `word_to_usage`, `dialogue_completion`, `meaning_in_context`,
and `sentence_rewrite`. `dialogue_completion` and `meaning_in_context` currently
support single-choice only. Do not invent typed variants to fill a matrix.

Test a native Decisions call with a short-answer or a genuinely nontrivial word
answer. Exact canonical single-word answers can use the backend's legitimate
no-model fast path; they are not evidence that live decision integration works.

### 10.4 Assistant

| File | Cases and assertions |
| --- | --- |
| `assistant/conversations.test.ts` | Create conversation; text/reasoning appears before completion; follow-up; checkpoint reload; history pagination without duplicates; confirmed/cancelled delete; valid image reaches native vision checkpoint and invalid images never become sent attachments. |
| `assistant/approvals.test.ts` | Pending mutation has not executed; pending survives reload; approve writes once, reject writes nothing; auto-approve preference persists and failed save leaves saved value; enabling auto-approve does not silently resolve an old pending decision; publication still requires consent; successful writes invalidate/update affected Library/settings views. |
| `assistant/context.test.ts` | Navigate then send a turn and assert the current resource/scope reaches the real tool path; known meanings render; another actor's private node/conversation/tool data stays hidden; read-only turn does not refresh unrelated account/Library queries. |
| `assistant/recovery.test.ts` | Cancel stream and send again; provider/tool/network failures including an error inside HTTP 200 SSE; remembered conversation deleted; busy conversation feedback; cancellation releases the real turn lease; attachment errors leave composer usable. Check stream completion/cancellation before reading final usage/checkpoint state. |
| `assistant/access-and-usage.test.ts` | Catalog/model/effort/vision UI and effective Free/Pro permissions from actual policy; ownership; exhausted allowance blocks new work; usage settles after completion/failure/cancel as appropriate; UI does not replay rejected work; reject pending mutation can finish without a newly admitted model call. Representative user-facing rate-limit recovery, not a duplicate burst/lease invariant suite. |

Do not assume every model/effort is Pro-only: assert the configured effective
policy. Usage settlement is asynchronous relative to partial text rendering; wait
for the native turn to terminate before final assertions. Public API reads remain
the primary persistence oracle, not raw checkpoint SQL.

### 10.5 Rendering and navigation

| File | Cases and assertions |
| --- | --- |
| `platform/server-rendering.test.ts` | No-JS contexts see real Home activity, Library node titles, dictionary data, settings values, public profile/collection content; resource title/metadata match visible content; request locale/theme appear in HTML; fresh hydration waits for interactive readiness and does not immediately repeat the initial domain reads. |
| `platform/navigation.test.ts` | Same-page filter/pagination/sort requests go to Pycil, not a Next RSC/action CRUD proxy; URL query state and Back/Forward stay coherent; client navigation/reload agree; mobile navigation/focus is usable; auth/session transition clears prior account cache. |

No-JS tests do not assert interactive operations work without JavaScript. SSR tests
must assert visible semantic content, not only text buried inside Next serialized
scripts. Absence-of-duplicate-read checks end after demonstrated hydration/interactive
readiness, not immediately after the first heading becomes visible. Avoid forbidding
legitimate link prefetch or new-route RSC traffic outside the same-page scenario.

### 10.6 Live models and separately selected external auth

| File | Cases and assertions |
| --- | --- |
| `live/generation.test.ts` | Real UI word generation, readable evidence-aligned senses/examples, inflected input normalization, search and reuse, then add generated meaning to a deck and study it. Confirm a clean target and actual generation before asserting reuse. |
| `live/grading.test.ts` | Pro short-answer via UI that necessarily invokes the native decision provider; meaningful expected diagnostics within semantic acceptance; submit persists review. Do not use the exact-word fast path as the only live decision case. |
| `live/assistant.test.ts` | Real model reads actual Library via tools, follows up, reopens checkpoint history; one safe owned mutation goes through approval and produces the actual persisted/UI result. |
| `external-auth/providers.test.ts` | Real Google OAuth callback using a dedicated configured identity and real enabled TOTP using an owned identity. Select explicitly; validate prerequisites before tests. |

Live tests use semantic assertions, not exact model prose, exact sense count, or
provider timing. Three fixed files define the live command; native API-only
inflection invariants are not relabeled as browser evidence. No controlled-provider
fallback is allowed in this profile. Missing provider credentials fails live setup.

Google/TOTP are not silently skipped inside the mandatory default suite. An
unselected external-auth project is reported as not run. An explicitly selected
project lacking required configuration fails its prerequisite check and reports
missing coverage. Borrowed persistent Google identities are not deleted; record
their ownership distinction from ephemeral Clerk identities.

## 11. Assertion and failure-injection rules

### Normal journey shape

1. Arrange an actor and the minimum data through fixtures/real APIs.
2. Act through the user-visible browser control for the behavior under test.
3. Assert the visible result and the relevant persistence/authorization through
   the public API, preferably after reload or in a second owned context.

Example: publish in owner UI, read as guest, save a subscriber reference, unpublish
as owner, then verify both guest read revocation and subscriber unavailable UI.

- Use semantic roles/names and meaningful unique fixture titles. Do not hide
  ambiguous data with `.first()` or nth-option answers.
- Prefer Playwright auto-waiting, request completion, controlled stream gates,
  and bounded polling over sleeps. Client clocks may support a local UI invariant;
  they do not control server time, JWT validity, or live model deadlines.
- Choose timezone data safely away from unstable boundary assumptions. Exhaustive
  exact midnight/date calculations remain backend unit/integration tests.
- Inspect direct HTTP requests only to protect real contracts: duplicate writes,
  read-only preparation, idempotency, affected query refresh, or direct API routing.
  Avoid brittle assertions against every benign SDK request.
- Do not use frontend parsers/helpers to verify the exact data those helpers
  generated. E2E setup can reuse product HTTP contracts without reusing runtime
  transport/state implementation.

### Failures worth exercising end to end

Allowed: abort a real targeted request; delay a genuine response and release it;
use `route.fetch()` to let the backend commit then drop the browser response;
controlled provider refusal/stream error; deliberately revoke an owned session;
corrupt the exact test-owned session storage in a storage-recovery case.

Not full-stack E2E: fulfill a Pycil route with fabricated business JSON and assert
a spinner/error component. Keep that pure UI boundary case in browser integration.

A lost-response test must prove the server accepted the request before aborting
the client response. Review submission has a real replay contract; deck creation
does not automatically acquire one. Preserve the actual behavior: one accepted
creation, retained uncertain draft/error, and reload revealing the persisted node.

## 12. Execution profiles, commands, and diagnostics

### Planned root-package commands

Run these from repository root after installing web and E2E dependencies:

```sh
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir e2e install --frozen-lockfile
pnpm --dir e2e exec playwright install chromium

pnpm --dir e2e test
pnpm --dir e2e test:live
pnpm --dir e2e test:mobile
pnpm --dir e2e test:webkit
pnpm --dir e2e test:external-auth
pnpm --dir e2e typecheck
pnpm --dir e2e run clean <run-id>
```

These are target commands, not currently installed commands. The default `test`
script explicitly selects default Chromium; it must not run every Playwright
project accidentally. Mobile/WebKit select a declared critical subset, live selects
only the three `tests/live` files, external auth selects its explicit directory.
Use Playwright's normal file/title selection for focused development; do not keep
an `E2E_GREP` compatibility environment or call a focused pass a full profile pass.

### Profile policy

| Profile | Scope | Infrastructure/models | Concurrency and retry |
| --- | --- | --- | --- |
| Default Chromium | All ordinary domain/platform/auth journeys | Fresh stack, real Clerk, controlled models, production web | Initially two workers, zero whole-test retries. |
| Mobile Chromium | Critical login/navigation, create/select meaning, Study recovery, public collection, Assistant send/approval | Fresh stack and controlled models | Two isolated workers; tagged focused cases, not the entire desktop matrix. |
| WebKit | Critical auth/publication/Study/storage/navigation/stream subset | Fresh stack and controlled models | Scheduled CI after installing the browser; not a claim of physical Safari/iOS testing. |
| Live | Fixed generation/grading/Assistant files | Fresh stack, real Clerk and external models | Small measured concurrency; no automatic whole-test retry. |
| External auth | Explicit Google/TOTP cases | Fresh owned application resources and configured identities | Conservative concurrency; required instance settings validated. |

Application retries/reask remain policy-owned. Do not change retry budgets or
weaken validation because a live test fails. Record each live run's selection,
first failure, elapsed time, and final result. A subsequent success is new evidence,
not proof the earlier timeout/invalid output did not occur.

### Explicit inputs

Required identity inputs: `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_ISSUER`,
`CLERK_JWKS_URL`; optional audience only if the instance requires it. Derive frontend
publishable-key input explicitly from the selected test configuration.

Live additionally requires `LLM_API_KEY`, `LLM_BASE_URL`, `DECISION_API_KEY`, and
`DECISION_BASE_URL`. Default mode injects only its controlled provider addresses
and disposable credentials. Application policy comes from current
`config/config.yaml`; do not copy the model catalog/prices into test source or
silently relax production policy to accelerate tests.

Pass variables explicitly via shell/CI or one documented runner-specific env source
if the implementation needs it. Do not search root `.env`, web `.env.local`, and
multiple fallback files for arbitrary deployment credentials. Never infer DB/Redis
targets from application environment; Compose creates the owned targets.

### Artifacts and failure reporting

- Separate run setup metadata/logs from Playwright's browser output and HTML/JSON
  reports. Use run-specific output roots so suites never delete each other's files.
- Record run ID, profile, selected cases, revision, resource IDs, timings, and
  setup/test/cleanup status without token-bearing URLs or credentials.
- Auth/password tests keep tracing off. Initial policy may keep traces off for all
  actual-Clerk E2E; enable domain failure traces only under an explicitly private
  artifact policy. Screenshots, console, provider prompts, and checkpoints can
  still contain sensitive data. Do not claim bearer redaction makes every trace safe.
- Use safe status/request-kind/error-type summaries, not raw SDK log dumps. Preserve
  necessary detailed logs privately with bounded retention/access.
- Teardown failures are visible even when all test assertions passed. Preserve both
  the original failure and any cleanup errors; do not replace one with the other.
- No broad console suppression. Permit only narrowly documented expected failures
  in the test intentionally injecting them.

## 13. CI and documentation changes

### CI

Update [the test workflow](.github/workflows/test.yml):

1. Web job continues unit/browser integration/typecheck/lint/build with its own
   dependencies and reports. It no longer starts product E2E through web scripts.
2. Root E2E default job installs both package lockfiles, builds the existing API
   Dockerfile through the owned Compose topology, installs Chromium, and runs the
   same root package command used locally. No host uv/Python is necessary solely
   to run the new orchestration/seed, which execute in the image.
3. Keep backend pytest/Testcontainers and the image/production Compose gates.
   Removing Python from E2E does not remove backend Testcontainers dependencies.
4. Trusted PR/push default E2E requires development identity inputs. Forks run
   secret-free jobs and explicitly lack real-identity E2E coverage. Do not expose
   repository secrets to untrusted PR code or bypass this with pull_request_target.
5. Live is manual/scheduled and separately reported; when requested, default
   evidence still runs or remains a separately required gate. Do not replace default
   coverage with live coverage or label manual success as a required PR check.
6. Nightly WebKit and selected mobile runs use explicit subsets and independent
   owned resources. Do not multiply every test across all themes/locales/devices.
7. CI always attempts owned cleanup and preserves safe failure summaries. Upload
   detailed artifacts only to an approved private destination/retention policy,
   not an automatically public raw log archive. Bound job timeouts and use
   cancellation handling plus identity-ledger recovery for interrupted runs.

### Documentation owners after cutover

Update the smallest existing owning surfaces, after reading them:

- `e2e/README.md`: authoritative E2E commands, fixtures, credentials, cleanup.
- `apps/web/README.md` and `apps/web/tests/README.md`: remove old E2E runner setup;
  link to root E2E; document only web-owned unit/browser integration commands.
- `docs/backend/testing.md`: replace the current statement that E2E belongs to
  `apps/web` with root product ownership; keep backend boundaries unchanged.
- `docs/backend/README.md`: point verification readers to current E2E docs where
  relevant; do not copy a phase completion record into business authority.
- `Makefile`: add explicit root E2E targets only if consistent with existing
  command ownership; do not change `make test-api` or silently make it paid.
- This document: record phase outcomes and actual verification evidence separately
  from the intended architecture.

## 14. Migration map: preserve behavior and remove old ownership

Inventory every current assertion before deleting its owner. Read business source
and lower-level coverage first; the old suite is a regression inventory, not the
blueprint for new implementation. Use a small execution ledger with old behavior,
new owner, and evidence of survival. Do not migrate by copying old runtime imports,
global identities, answer-oracle helpers, or fixture ID conventions.

| Current E2E file/group | New owner(s) |
| --- | --- |
| `authentication.test.ts` | `auth/*`, `platform/navigation`, selected `external-auth/providers`. |
| `account-profile.test.ts`, `account-settings.test.ts` | `account/profile`, `account/preferences`, targeted SSR readiness regression. |
| `learning-journey.test.ts` | `public/landing`, mobile critical selections, `study/session`; do not retain a duplicate giant smoke test. |
| `home-reporting.test.ts` | `home/dashboard`; exact dedup/timezone math retains backend integration ownership. |
| `library-management.test.ts` | `library/editing`, `library/publication`, `library/references`, `discovery/public-library`; API-only mutation invariants to existing backend owners. |
| `library-browsing.test.ts` | `library/browsing`, `platform/navigation`. |
| `library-references.test.ts` | `library/references`; exhaustive logical-cycle/provenance pagination internals retain backend scope/sense-page owners. |
| `published-library.test.ts` | `library/publication`, `discovery/public-library`, public SSR; keep direct public study with no Personal save. |
| `dictionary.test.ts`, `word-generation.test.ts` | `vocabulary/dictionary`, `vocabulary/generation`. |
| `study-entry.test.ts` | `home/dashboard`, `study/session`, `study/recovery`, entitlement case in preferences. |
| `study-questions.test.ts` | `study/question-types`, bounded retry/recovery; legal pair/scoring matrix remains lower-level. |
| `study-recovery.test.ts`, `flashcards.test.ts` | `study/recovery`, `study/flashcards`; retain page-two and frozen replay regressions. |
| `assistant-conversations.test.ts` | `assistant/conversations`, `assistant/context`, `assistant/access-and-usage`. |
| `assistant-approvals.test.ts` | `assistant/approvals`. |
| `assistant-recovery.test.ts` | `assistant/recovery`, `assistant/access-and-usage`; API-only burst/lease invariants remain backend integration. |
| `server-rendering.test.ts` | `platform/server-rendering`, `platform/navigation`. |
| `llm-provider.test.ts` | Three `live/*` files; API-only provider contracts do not masquerade as browser journeys. |
| `auth.setup.ts`, `fixtures.ts`, `helpers/*`, `support/*`, `run.py` | Replaced by root lifecycle/fixtures/support, then deleted; no legacy forwarding files. |

### Existing backend owners to check before moving invariant assertions

- Library membership concurrency/invalid rollback/system roots/move cycles:
  `apps/api/tests/integration/library/test_mutations.py`.
- Physical/live access and publication/reference revocation:
  `.../library/test_access.py`, `test_publication.py`, `test_scopes.py`.
- Cursor/provenance/filter invariants: `.../library/test_sense_pages.py`.
- Real account provisioning and sparse preference/handle race behavior:
  `.../account/test_identity.py`, `test_settings.py`, `test_profiles.py`.
- Prepare/grade read-only behavior, artifact validity, submit replay/concurrency:
  `.../study/test_preparation.py`, `test_grading*.py`, `test_artifact_banks.py`,
  `test_reviews.py`, `test_progress.py`.
- Native checkpoint/approval/stream/lease invariants:
  `.../assistant/test_checkpoints.py`, `test_approval.py`, `test_stream.py`,
  `test_leases.py`, `test_http.py`.

Check each actual assertion, not merely similar test names. Extend an existing
backend integration owner only when a material invariant would otherwise be lost.
Do not duplicate an already sufficient test just because it used to live in E2E.

## 15. Implementation phases

Use this accepted design as the work contract. Keep execution notes/status concise;
do not create a second competing architecture plan or unrelated system redesign.

### Phase 1 — Confirm scope and establish the independent package

- Reconcile current workspace changes and the exact source/test inventory.
- Capture the migration/coverage ledger and installed tooling versions.
- Add root package, lockfile, TypeScript configuration, explicit projects, ignored
  artifacts, and production webServer configuration.
- Separate Next build output from development using supported distDir behavior.
- Keep legacy execution available only during this unfinished migration; do not
  ship aliases or count both suites as independent coverage.

Validation: package/typecheck/config collection; prove correct project selection
without creating containers on config import; ensure `--list`/help do not require
running infrastructure, and require credentials only for actual selected execution.

### Phase 2 — Prove actual lifecycle before writing all journeys

- Implement Compose stack, real API image/migration/reference gate, controlled
  provider profile, initial semantic manifest, and global setup lifetime.
- Implement finite seed operations and exact owned cleanup.
- Implement official Clerk setup and one fresh actor through real provisioning.
- Prove production Next can become static-ready before backend global setup.
- Exercise a minimal representative browser journey against the actual stack.

Validation: normal startup/teardown; migration failure; API readiness failure;
occupied port; fixture failure; graceful interruption. Prove no owned servers,
containers, volumes, contexts, or Clerk identities remain after normal/failing
execution. Verify sensitive setup metadata is ignored and not printed. Abrupt
kill recovery limitations must be documented, not hidden.

Do not retain a meaningless stack-is-up test just to increase count. Put the proof
in a real journey (for example create/reload a deck) and use finite support checks
for the lifecycle branches.

### Phase 3 — Make fixtures and model scenarios genuinely independent

- Implement test-scoped actor/secondary/guest fixtures and exact identity ledger.
- Implement independent token-backed API client and real API resource setup.
- Seed plan/usage/due states after provisioning with correct actor invalidation.
- Implement semantic data/answer expectations and reserved mutable resources.
- Implement native provider surfaces, scenario registration/matching, stream gates,
  and required-call/unexpected-request checks.

Validation: two mutation tests in parallel with different actors/scenarios; a
deliberately failing first scenario followed by an unaffected second; Pro/exhausted
state observable through public API; two concurrent reserved generations cannot
consume each other's response sequences. Add focused support checks for newly
written matching/validation/cleanup logic.

### Phase 4 — Implement domain journeys

Suggested order: public/auth/account → Library/publication/Discovery → Vocabulary
→ Study/Home → Assistant. Implement the file inventory in Section 10 with focused
cases and source-aligned assertions. Retain all named existing valuable regressions.

Validation: narrow changed-domain default runs first, then all implemented default
cases with two workers. Remove ordering assumptions before broadening. Verify
prepare/grade/read-only browsing do not write progress, writes persist on reload,
and cross-user/public revocation outcomes use genuine HTTP authorization.

### Phase 5 — Rendering, navigation, mobile, and live boundaries

- Complete no-JS, locale/theme, fresh hydration, direct API, URL/history, and
  account-cache isolation journeys.
- Define a fixed mobile/WebKit critical subset using declared case metadata, not
  an arbitrary title grep embedded in CI.
- Implement three fixed live files, clean targets, actual provider-call evidence,
  semantic expectations, and explicit external-auth prerequisite reporting.

Validation: all default Chromium, mobile subset, WebKit subset, fixed live suite
when requested/configured. Preserve every live run result; no hidden retries or
controlled fallback. Report external-auth selected/not-run/missing-config separately.

### Phase 6 — Cut over CI/docs and delete obsolete code/config

This is required implementation work, not optional follow-up cleanup.

- Reassign API-only invariants using Section 14; verify their surviving assertions.
- Update web scripts so web-owned `test` covers only its ordinary unit/integration
  levels; root E2E has its own explicit command. Keep Playwright browser integration.
- Remove E2E/auth-setup projects and `E2E_BASE_URL`/profile/grep branches from the
  web Playwright config. Its only remaining browser suite is web integration.
- Replace current frontend-E2E CI ownership/commands with root E2E jobs.
- Update current test/setup documentation and command navigation.
- Delete the entire old `apps/web/tests/e2e/` tree, including runner, Python provider,
  seed, monkey-patch helper, localStorage answer oracle, and shared A/B/C fixtures.
- Remove now-unused `@clerk/testing` from web dependencies if only root E2E needs
  it; keep product Clerk packages. Remove duplicate direct Playwright dependencies
  only after checking their remaining callers and integration commands.
- Keep Python Testcontainers in backend dev dependencies: backend integration
  still uses it. Do not remove a dependency based solely on leaving E2E.
- Regenerate affected lockfiles with the appropriate package manager; no manual
  dependency-lock editing or unexplained stale entries.
- Remove obsolete environment names/example values and runner-only flags from
  scripts, CI, docs, and support configuration. Do not delete legitimate product
  `LLM_*`, Clerk, DB, or CORS configuration.
- Remove snapshot-specific `.pycil-e2e-web-*` ignore entries when no caller remains;
  ignore the new owned `.artifacts` and `.next-e2e` output. Retain web test-results
  ignores because browser integration still produces them.
- Remove abandoned generated files, empty folders, reports accidentally placed in
  source, duplicate fixture payloads, and test-only production exports/hooks left
  without a real caller. Never remove unrelated user changes or recovery evidence.
- Remove migration-period compatibility scripts/aliases and the retired command
  paths. Do not keep a deprecated runner as a silent fallback.

Validation: source/config/docs caller scan confirms no active old runner/import/
script references; root and web collection each contain only their intended tests;
fresh dependency install and commands work without the old directory. Historical
execution reports may mention old paths as history; do not erase them or add a
test whose only purpose is banning a filename/string.

### Phase 7 — Final verification and review

- Focused support checks and affected backend integration tests first.
- Root E2E TypeScript checks, web type/lint/build checks affected by configuration,
  and surviving frontend unit/browser integration checks.
- Full default Chromium with two workers from a clean disposable stack; run a
  second independent default invocation to detect residual remote/shared state.
- Explicit mobile and WebKit critical runs; configured fixed live suite; selected
  external auth or truthful not-run/missing-prerequisite result.
- Validate CI Compose/collection/install commands and cleanup/privacy behavior.
- Review connected code for ownership, retry policy, fixture leaks, runtime imports,
  provider fallbacks, meaningful assertions, and unused abstractions/dependencies.
- Compare every inventory row and completion criterion with actual evidence.
  Report commands, profiles, pass/fail/skip counts, failures, and resource cleanup.

Do not weaken assertions, serialize the suite, extend every timeout, hide a failing
check, or run live repeatedly until one success is presented without its history.

## 16. Acceptance checklist

- [ ] Root E2E package is the sole owner of product browser journeys.
- [ ] Config import/collection does not start infrastructure or create identities.
- [ ] Production frontend build/start uses an isolated supported output directory.
- [ ] Real migration/reference/checkpoint/search startup gates are exercised.
- [ ] Partial setup and fixture failure clean all reachable owned resources.
- [ ] Fresh actors/scenarios work with two workers and independent runs.
- [ ] Actor seed invalidates the correct cache; no SQL-after-startup lexical bypass.
- [ ] Meaningful data and independent answers replace magic IDs/session oracles.
- [ ] Every ordinary test inventory behavior has a verified owner.
- [ ] Shared generated/cold resources cannot cross-contaminate scenarios/projects.
- [ ] No Pycil successful-response mocking is misreported as full-stack E2E.
- [ ] Stream, approval, usage, replay, publication revocation, and page-two recovery
      regressions survive.
- [ ] Visible SSR and direct browser→Pycil interactions have real-stack evidence.
- [ ] Fixed live scope and external-auth prerequisites report truthful coverage.
- [ ] CI and docs use the new commands; required jobs retain honest boundaries.
- [ ] Old E2E tree/runner/config/scripts/unused dependencies and aliases are removed.
- [ ] Fresh installs, collection, affected lower-level tests, and selected E2E
      profiles pass; failed/skipped/unrun checks remain explicit.
- [ ] No credentials/auth state/private artifacts are tracked; no owned resource
      remains after normal teardown, and interrupted-run recovery is documented.

## 17. Risks, unresolved proof, and rollback boundary

- The proposed startup order has source/tooling support but still needs the Phase 2
  actual-stack proof, including production build and finite one-shot container waits.
- Per-test Clerk users trade setup latency/rate-limit pressure for independence.
  Start with two workers and measure. Do not revert to shared mutable users to hide
  a performance problem; a measured account-per-worker design would need explicit
  reset/isolation proof before changing this decision.
- Shared vocabulary and in-process artifact caches require reserved mutation
  resources in addition to actor isolation. Review browser/project parameterization.
- Live models can timeout or emit invalid output. A successful browser run proves
  that journey at that time, not provider reliability or production capacity.
- Automatic container cleanup cannot guarantee remote identity deletion after host
  death. Keep a private exact ownership ledger and a finite recovery operation.
- Docker image builds, native dependencies, development identity availability, and
  external OAuth/MFA settings can fail before browser assertions. Report these as
  infrastructure/prerequisite failures, not product passes.
- Artifact privacy is an operational responsibility. Disable unsafe collection
  rather than assuming a superficial sanitizer removes every secret.

Rollback is a source-control rollback of the focused testing/config change and
deletion commit, not a permanent compatibility runner. All E2E application data is
disposable; this redesign must not migrate or destroy user/deployment data. Preserve
unrelated workspace work and do not commit/push without the user's instruction.

## 18. Documentation references consulted

- [Playwright authentication isolation](https://playwright.dev/docs/auth).
- [Playwright fixtures](https://playwright.dev/docs/test-fixtures).
- [Playwright webServer lifecycle](https://playwright.dev/docs/test-webserver).
- [Playwright global setup/teardown](https://playwright.dev/docs/test-global-setup-teardown).
- [Playwright best practices](https://playwright.dev/docs/best-practices).
- [Testcontainers Node Compose support](https://node.testcontainers.org/features/compose/).
- [Testcontainers wait strategies](https://node.testcontainers.org/features/wait-strategies/).
- [Clerk Playwright helpers](https://clerk.com/docs/guides/development/testing/playwright/test-helpers).
- Installed Next.js `distDir` and environment-loading documentation under
  `apps/web/node_modules/next/dist/docs/01-app/`; these were checked for build-path
  constraints and environment precedence.

No application code was changed and no tests were run during initial design
preparation. Implementation evidence is recorded separately below.

## 19. Implementation record — 2026-10-13

### Completed pilot work

- Created the independently locked `e2e/` TypeScript package with Playwright and
  Testcontainers Node Compose. Config collection starts no infrastructure.
- Added production frontend build/start through Playwright, disposable PostgreSQL,
  Redis and API image, actual migration/checkpoint/reference gates, and API health
  readiness. Ordinary development servers and ports are preserved.
- Committed a seven-word genuine reference subset with immutable source IDs and a
  small distinct lexical baseline. Seed emits semantic IDs before search startup;
  accounts/roots are provisioned through the application rather than inserted.
- Created fresh Clerk actors and lazy secondary/guest contexts, real token-backed
  HTTP setup/assertions, owned resource cleanup and an exact remote identity ledger.
- Added native controlled protocol scenarios with per-scenario consumption and
  unmatched-call failure, finite support checks, cleanup checks, and an explicit
  interrupted-run identity recovery command.
- Local credentials were copied, with user authorization, into ignored `e2e/.env`
  with mode 0600. Only this dedicated file is loaded; CI can supply environment
  variables. No application dotenv search remains in the new package.
- Implemented ten initial browser journeys across public, sign-in, account profile,
  preferences, Library editing/publication, no-JS SSR, and direct API filtering.
  These are an initial subset of Section 10, not completion of its inventory.

### Findings and design refinements

- The real production frontend became statically ready before backend global setup,
  validating the proposed webServer-first startup order for this revision.
- Seed initially failed both Python module resolution and SQLAlchemy registration.
  Its container now receives the packaged application path and calls the existing
  `register_models()` function; no substitute schema or migration was introduced.
- Completed Compose dependency containers are omitted from Testcontainers 12.2's
  running-container list. Compose's completed-successfully gates are retained and
  the owned migration/baseline exit states are explicitly verified. Do not claim
  a configured wait strategy necessarily inspected an already exited container.
- Testcontainers tears down a failed Compose startup before the caller can always
  read its logs. Setup CLI failure remains visible; baseline stores its finite safe
  failure type in run-owned artifacts when reachable. Do not report empty setup
  logs as proof that the application had no error.
- Next also regenerates `next-env.d.ts` and updates TypeScript includes. E2E now
  prepares one ignored run-specific TypeScript configuration. The ordinary root
  web tsconfig is preserved. Following installed Next documentation, generated
  `next-env.d.ts` is removed from Git tracking and web typecheck runs `next typegen`
  before `tsc`. Next can still regenerate this shared development declaration;
  E2E's own checker does not import it.
- Playwright workers import configuration without the original CLI arguments.
  The explicitly selected profile is inherited through the run environment, so
  worker config cannot accidentally choose a different controlled/live profile.
- Reload exposes SSR before the browser Clerk SDK is ready. The E2E API client
  explicitly waits for a real current session and refreshes its token per call.
  Colon action paths use relative URL resolution rather than being parsed as schemes.

### Verification to date

- Frozen package installation, root TypeScript checking, support checks and lint
  passed. Web typecheck passed after the build configuration change.
- Default Chromium pilot ran with two workers, production Next and disposable
  stores: nine journeys passed, then a separate expanded run passed ten journeys
  including publication cancellation and guest/reference access revocation.
- Earlier pilot failures are retained privately: seed startup failures, helper URL/
  hydration mistakes, an incorrect accessibility locator, and config validation in
  worker processes. They were corrected at their owner; no assertion weakening or
  whole-test retry was added.
- Normal tested teardown removed run-owned containers and released 3200/8100/8110.
  Existing application containers and development ports were left untouched.
- Final pilot on unchanged runtime/test source: ten journeys passed with two
  workers in 1.4 minutes. Its ledger recorded eleven created identities and eleven
  successful deletions, no unreconciled IDs, and completed global cleanup. Two
  finite support checks passed; E2E TypeScript/lint and web typecheck passed.
  Exact identity recovery was idempotent on that ledger. The finite build cleanup
  command removed only its completed run output and retained private diagnostics.
  Use `pnpm run clean`, because pnpm 12 reserves the bare `clean` command.

### Historical pilot boundary (superseded by the continuation records below)

At the pilot boundary, Phase 1 is implemented. Phase 2's normal lifecycle is proven; its remaining injected
failure/interruption cases still need proof. Phases 3–5 are partially implemented:
actor/scenario foundations exist, while actor plan/usage/due preparation, question
artifacts/answers, remaining Library/Study/Home/Assistant journeys, native stream
gates, live and external-auth coverage are pending.

Phase 6 has **not** been executed. The old web E2E tree, web execution commands and
CI ownership remain temporarily during migration. Do not delete their regressions
until the coverage ledger and lower-level ownership checks are complete. The final
cutover must remove them and all obsolete configuration/dependencies; this is not
permission to ship parallel legacy execution. Phase 7 full-suite verification is
also pending. No commit or push has been made.


### Expanded implementation and verification — continuation

The root suite now includes authored question artifacts, 101 distinct pagination
meanings from genuine reference rows, actor-specific plan/usage/due preparation,
per-scenario held structured responses and SSE gates, eight single-choice question
types, typed answer journeys, study recovery, Assistant approvals and tools,
Home, Discovery, Dictionary and generation journeys. No successful Pycil response
is fulfilled by a browser mock.

An expanded immutable default run recorded **35 passed / 7 failed**. Subsequent
focused runs proved flashcard page 101, dictionary additions, copy independence,
word pagination/history, native approval/rejection and auto approval, stream
settlement usage and cross-account checkpoint access. Failures in helper labels,
pagination settling, error-document assumptions and native AG-UI quota assertions
were identified at their owner. A transient browser `ERR_NETWORK_CHANGED` and a
Clerk CDN chunk failure remain recorded as failures rather than suppressed.

An interrupted live run was not counted as evidence. Its surviving production
Next process was stopped and exact run-ledger identities were reconciled before
another stack started. The resumed fixed live profile has proved the real
Assistant read/checkpoint/approved-write journey and real decision grading;
generation also passed. The resumed fixed live run recorded **3 passed** in
2.7 minutes on a production frontend and disposable real backend stack.

The application now configures the native OpenRouter SDK with `retry_config=None`
when Assistant retry is disabled. Inspection of the installed SDK showed that
LangChain's `max_retries=0` otherwise retained the SDK default 5xx retry policy.
The constructor/resource-close unit regression passed. Four finite provider
support checks passed, including explicit stream/structured hold release and
occupied-port failure. Final full-suite verification and legacy cutover are still
required; this continuation is not a completion claim.


The next expanded run recorded **51 passed / 6 failed** across 57 ordinary
journeys. All eight single-choice types, both typed answer formats, native dynamic
sense decisions, Home deduplication, page-101 flashcards, approval persistence,
auto approval, usage settlement, tool authorization failure recovery, prepare
retry, pause, early finish, storage failure and tab conflict passed. Six remaining
helper expectations were corrected: quota endpoint/status, file-chooser lifecycle,
guest copy-link versus mutation permissions, move navigation to the destination,
nonempty Home SSR data, and the explicit Retry grading action. Their rerun is
pending. Backend ownership checks recorded 16 integration passes for Library
mutations/publication/scopes and 31 Assistant unit passes.

External Google/TOTP journeys are now defined in their separate profile. They
require explicit dedicated Google credentials and enabled development TOTP;
missing prerequisites fail selected coverage rather than silently skip. Those
external journeys have not been run. Legacy deletion, CI/docs cutover, remaining
inventory gaps, final default/live/mobile verification, review, commit and push
remain outstanding.


The focused repaired run recorded **17 passed / 1 failed**. Quota correctly returns
HTTP 403 from `/assistant:run`; the prior speculation about HTTP 200 at admission
was incorrect. Discovery search/navigation, guest copy-link without mutation
permission, reference saving/study, move destination navigation, authenticated
Home/Dictionary SSR, early finish, tab/storage recovery and explicit grade retry
passed. The sole failure was an assertion expecting an image data URL in a native
AG-UI checkpoint: upload reached the model and persisted the real MIME/base64
image resource. The assertion now verifies that native shape. Further inventory
journeys cover Free/Pro typed entitlement, separate interface/translation language,
account transition cache isolation, direct public study without Personal saving,
and locale/theme cookies in no-JavaScript server HTML; final verification is pending.

Web unit tests passed **47 tests in 23 files**. No failures were suppressed and no
whole-test retries were added. Cleanup/cutover and commit/push remain outstanding.


### Cutover ledger — 2026-10-13

The old suite was read as a regression inventory after new journeys were derived
from business source. The following are the surviving owners. Exact API-only
invariants remain in backend integration, rather than being driven through a
browser helper. New browser owners are under `e2e/tests/`.

| Retired behavior | Surviving owner and assertion |
| --- | --- |
| Guest navigation, protected workspace, safe return routes | `public/landing`, `auth/sign-in`, `auth/sign-up`; visible destinations and real identity provisioning |
| Incorrect password/unknown identity, verification/resend, reset | `auth/sign-in`, `auth/sign-up`, `auth/password-reset`; rejected credentials/code, replacement password |
| Token refresh, new tab, account switch, session revocation | `auth/sign-in`; real Clerk session and private cache boundary |
| Google callback and enabled TOTP | `external-auth/providers`; explicit credentials/enabled feature required, not silently skipped |
| Profile persistence/rename/duplicate, preference persistence/draft/entitlement | `account/profile`, `account/preferences`; public lookup, native patch, preserved draft, Free/Pro and locale separation |
| Profile draft while authentication loads | `apps/web/tests/integration/browser/profile-settings.test.ts`; controlled UI timing remains a browser integration concern |
| Account provisioning, sparse patches, handle races | `apps/api/tests/integration/account/test_identity.py`, `test_profiles.py`, `test_settings.py`; real database constraints and concurrent provisioning |
| Home counts/timezone/dedup/schedule after review | `home/dashboard`; actual submitted review and visible dashboard; exhaustive math in backend `study/test_progress.py` |
| Home section outage/retry, never replace errors with zero | `apps/web/tests/integration/browser/home-dashboard.test.ts` (“independent errors never masquerade as zero”); UI failure owner |
| Deck create/rename/move/copy/delete/cancel/lost accepted response | `library/editing`, `library/publication`; target action through UI and independent persistent memberships |
| Atomic delta concurrency, invalid batches, protected roots/cycles/quota rollback | Backend `library/test_mutations.py`; concurrent growth, exact quota, system/foreign node and closure assertions |
| Logical reference cycle and distinct scope | Backend `library/test_scopes.py`; cycle termination and no duplicate membership |
| Live reference versus independent copy | `library/references`, `library/editing`; source edit updates reference, copy remains independent |
| Source deck pagination/canonical links | `library/references`; 22 distinct visible source links with exact expected destinations; seek invariants in backend `library/test_sense_pages.py` |
| Publication cancellation/consent/retained reference/subtree/guest revocation | `library/publication`; guest page and reference availability after unpublish/delete |
| Discovery filtering/page two/direct public study/private denial | `discovery/public-library`; real public pagination, foreign content read-only and direct Study without a Personal save |
| Word/scope pagination, search/sort/filter/breadcrumb/history/stale request | `library/browsing`, `platform/navigation`; settled native reads, page boundary, latest response and canonical URL |
| Dictionary picker selection across queries, concurrent addition, nested new deck | `vocabulary/dictionary`; semantic senses, real batched reads and memberships, real deck creation |
| Ready versus reference, aliases/forms/POS detail | `vocabulary/dictionary`; genuine color/colour alias, banked/banking forms, distinct authored meanings |
| Generation validation, rejection/retry, pending, search publication/reuse | `vocabulary/generation`, `live/generation`; real inventory/enrichment and Tantivy. Expression normalization and exhaustive contracts remain backend `vocabulary/test_generation.py`, `test_search.py`, `test_jobs.py` |
| Study entry from Home/scope, Learn/Review/Practice, entitlement | `home/dashboard`, `study/session`, `account/preferences`; real due state and legal format policy |
| Eight choice types and six legal typed pairs | `study/question-types`; authored answers and native grading. Dialogue is choice-only by `QUESTION_FORMATS`, so no unsupported typed dialogue is invented |
| Initial preparation/grade do not write progress; submit does | `study/session`, `study/question-types`, `study/recovery`; public progress/activity before and after submit |
| Pause/reload/early finish/don’t know/retry/conflicting tabs | `study/session`, `study/question-types`, `study/recovery`; visible feedback/draft and one accepted activity |
| Broken/outdated saved data, storage denied, delayed prepare exit | `study/recovery`; storage access is deliberate only for recovery faults, never an answer oracle |
| Cold artifacts/model rejection/retry | `study/recovery`; unseeded archive target, native model protocol, validated artifact and real retry |
| Frozen accepted submission/lost response/idempotent replay | `study/recovery`; same idempotency key, one activity event; exhaustive replay/concurrency in backend `study/test_reviews.py` |
| Typed scoring/attempt cap/legal matrix/invalid artifact | Backend `study/test_grading.py`, `test_grading_branches.py`, `test_artifact_banks.py`; frontend `tests/unit/study-session.test.ts` owns the browser round cap |
| Flashcard read-only, page-two/reload/account position | `study/flashcards`; 101 distinct senses, reveal/navigation and unchanged progress |
| Stream before finish/reasoning/native history/follow-up/checkpoint/delete | `assistant/conversations`; explicit stream gate, genuine persistence and history pagination |
| Valid/invalid attachment and policy/usage/ownership | `assistant/conversations`, `assistant/access-and-usage`, `assistant/context`; native image checkpoint, allowance settlement and foreign denial |
| Pending mutation reload/approve/reject/auto approval/publication consent | `assistant/approvals`; real tool writes and publication service confirmation; `assistant/access-and-usage` rejects already pending work after exhaustion without another model request |
| Provider/tool error, cancel, deleted remembered conversation | `assistant/recovery`; next turn works, private tool target remains inaccessible |
| Busy conversation/burst/leases/checkpoint invariants | Backend `assistant/test_leases.py`, `test_stream.py`, `test_http.py`, `test_checkpoints.py`; real Redis and PostgreSQL concurrency |
| Visible no-JS domain/public rendering/metadata/locale/theme | `platform/server-rendering`; actual HTML content, request cookies and resource title |
| Fresh hydration/no duplicate reads/direct API filter/no Next CRUD proxy | `platform/server-rendering`, `platform/navigation`; browser requests and hydrated controls |
| Mobile workflow/navigation/focus | Critical mobile project plus `platform/navigation`; small viewport and native focus restoration |
| Real provider generation/grading/Assistant | Fixed three-file `live` project; earlier 3/3 pass remains historical, expanded generation-to-Study requires a new final run |

Cutover changes web scripts/config/dependencies, CI ownership and owning README
surfaces together. The old `apps/web/tests/e2e/` tree and Python runner/provider
are deleted. Root E2E is the sole product browser owner. Verification is still
pending after this cutover; the migration ledger does not itself prove a pass.


### Verification after cutover — in progress

- Typed/approval focused run: 19 passed with two workers, including all six legal
  typed pairs, dynamic native decisions and publication consent under auto approval.
- New-regression run was interrupted after seven recorded cases. Two auth failures
  were strict locator ambiguity with Next's route announcer; session revocation
  read Clerk before hydration. These test bugs were fixed with an error-specific
  locator and the native loaded/session readiness gate. This is not a full pass.
- Cutover builds exposed the old E2E imports after removing web's Clerk testing
  dependency, followed by its orphaned monkey-patch unit test. Both obsolete owners
  were deleted rather than excluded from TypeScript or kept as compatibility code.
- Frozen web/root installs and root typecheck passed. Four provider/port support
  checks passed. The new default inventory collects 88 cases in 25 domain files.
- The interrupted run's exact identity ledger was reconciled; only the four
  application containers remain outside the new suite. Failed setup builds created
  no backend containers/identities. Their diagnostics are retained privately.
- The two full default runs, updated fixed live, mobile/WebKit and final lower-level
  gates remain pending. No commit/push or full completion claim is made here.


### Resumption after interruption

The first full cutover invocation was interrupted after 37 recorded cases, with
one actor setup failure (`ERR_NETWORK_CHANGED` even on the bounded second GET).
It has no terminal pass report and is not counted as a full run. The owned Next
process on 3200 was stopped; the exact Clerk identity ledger was reconciled.
A separate concurrently running backend agent was starting Docker test containers,
which generated host network-change notifications. Final browser runs should occur
once those container lifecycle operations have finished; no user networking or
other session process is killed to obtain a green run.

Frontend integration returned 97 passed / 2 failed. Both failures reached visible
SSR controls before hydration: search input lost its initial edit and keyboard
activation had no handler yet. Dictionary/Library search and meaning triggers now
use React's server/client snapshot to stay disabled until hydration; rendered data
remains visible with JavaScript disabled. The existing browser assertions verify
that the first edit/keyboard activation works, rather than adding arbitrary sleeps.


### Connected review and focused gates

Ponytail Review traced actor creation → native Clerk token → public API, scenario
registration → external protocol → Instructor/LangGraph, native Compose migration /
seed / health gates, teardown and all package/CI callers. The assumed load is one
explicit local/CI run with two concurrent workers and separate scoped actors.

The review found the retired web monkey-patch test/dependencies, removed during
cutover. It also found a hand-written TOTP parser without a check; the small shared
authenticator helper now passes all six RFC 6238 SHA-1 vectors and invalid-secret
cases (five total finite support checks). No public test-only backend API was added.
A previously reported `side-tab` design finding is suppressed only for the shell
rail: its border marks the `aria-current` navigation link, not a decorated card.
No UI rule/file-wide suppression or confirmed-user claim was introduced.

Backend unit: 255 passed. Frontend unit: 46 passed after deleting the retired
monkey-patch test. Root/web typecheck and Ruff/format passed. Backend integration
initially returned 167 passed / 2 failed: cached structlog processors bypassed
`capture_logs` in the two Redis-failure tests despite genuine production events.
Their capture fixture now binds a fresh logger within capture; focused generation
integration returned 17 passed. A full recheck is pending.


### Lifecycle failure evidence and lower-level recheck

- Native `startStack(false)` rejected a real migration container exit 1 after an
  intentionally missing reference input (`5c4a8ec1794f4849b6e8ef4c2d1903a6`).
- Native startup rejected a deliberately failing API healthcheck as unhealthy
  (`01c569e1d9324601820af8372d937fe3`). The real migration/baseline ran first.
- Both finite probes asserted no exact-project containers/volumes remained and
  ports 8100/8110 were free. They restored the Compose source in `finally` and
  retained private error/cleanup evidence. The probe script lives only in `/tmp`,
  not as a second application runner or test-only product configuration.
- Earlier probes checked rejection/cleanup but lacked captured root-cause evidence;
  only the two confirmed runs above prove the requested failure branches.
- Full backend integration recheck: 169 passed, with 12 upstream LangGraph
  deprecation warnings. The capture failure was corrected without relaxing the
  required event/privacy assertions. Full default now collects 90 meaningful cases.

### Final default failures and focused correction

Run `8cb2296e6a1541daab42a32c69a08467` completed with 86 passed / 4 failed,
zero retries/skips, and successful teardown. Two model-selection tests attempted
to choose effort after selecting a model had closed the popover. They now reopen
it before choosing effort, preserving the actual provider request assertions.
The revocation test incorrectly required an absent level-one heading for its
negative assertion; it now verifies the private heading is absent and restores
authentication in `finally` so resource cleanup can run even after failure.
Account switching encountered an opaque native Clerk ticket-helper failure.
The auth journey now signs in through the actual password/verification form,
also reused for restoring the original actor, rather than bypassing that flow.

Focused auth/model run `643ccc4bd6e14313b8a0947fb23ff1eb`: 11 passed, no
retries/skips, successful teardown. Typecheck, focused lint and all five support
checks passed. The complete default recheck is running; no full-pass claim is
derived from this focused result.

GitHub currently reports no repository Actions secrets. Local real Clerk/live
credentials remain in the ignored dedicated environment; they are not uploaded
or committed. The remote credential-dependent E2E job requires configuring those
secrets before it can run successfully.

The next complete default invocation (`2f80bcbf817d49ba8802938eb18b9a47`)
finished with 89 passed / 1 failed and successful cleanup. All four previous
regressions passed; the single failure occurred during actor setup in Clerk's
email-based helper, which discarded Backend API status/codes and returned an
empty message. Setup now creates a native short-lived sign-in token for the
already-known user ID and passes it to the official testing helper's supported
ticket strategy. This removes the unnecessary backend email lookup. Native
identity errors retain status/codes while excluding provider messages/metadata;
a finite privacy check covers that diagnostic branch. No retry was added, and
the upstream failure is not assumed to be rate limiting without status evidence.

Run `d63b4d49f8a2425da8ca8e3c2d0336b8` also ended with 89 passed / 1 failed,
successful teardown and no whole-test retries. Its JSON report located the
failure in `createIdentity` and retained the native SDK error array:
`unexpected_error: fetch failed`. This proves a Node transport failure while
creating the secondary Clerk user, before the business test, rather than a
Pycil assertion or a confirmed HTTP rate limit.

Identity creation now catches only that native transport failure, checks the
exact reserved email, reuses a committed user if present, and otherwise permits
one further creation attempt. It logs the recovery. No other error/test retry is
added. Finite native-SDK HTTP checks prove lost-response recovery, no duplicate
creation, successful bounded retry, no retry on validation rejection, and failure
after the second transport error. All ten support checks and type/lint checks
passed. The final independent default/live/mobile/WebKit chain is running on this
source revision; earlier failures remain recorded above.

The first recovered-identity default invocation
(`eeec47f061fc4b0dbafad591c7b7f767`) passed all 90 cases in 5.7 minutes, with no
whole-test retries, skips or identity recovery. Teardown succeeded, all recorded
identities were reconciled, and Docker reported zero owned containers/volumes.
The second (`ecac987282b949ce8907bf402896d951`) passed 89 and failed one fixture.
Its report proves the Assistant follow-up completed; the failure stack was in
`deleteIdentity`, with the native `unexpected_error: fetch failed` array. Cleanup
reconciled the identity afterward. This is not a second complete pass.

Owned identity deletion now permits one retry of that transport failure, treats
404 as already removed, and fails validation/permission or repeated transport
errors. Failed actor setup uses the same owned deletion path and ledger. Five
native-SDK HTTP checks cover normal deletion, initial 404, lost committed response,
403 without retry, and failure after the second transport error. All 15 finite
support checks, typecheck and focused lint passed. The fixed live suite runs first
in the next verification chain, followed by two default invocations and critical
mobile/WebKit; no test or model result is automatically retried.

### Final cleanup and cross-browser verification

- Fixed-source independent Chromium runs `76a30b6f8b1b4b119e39757fd2292db6`
  and `9ecd709215804d71a6a804e5c7b57ce3` each passed 90/90, with zero
  test retries, skips, or flaky results. Live run
  `adf9b76a70bc4c2ba2d74f9651c05acb` passed all three fixed journeys; mobile
  `0e1a4b42b56f4bbaa140a3e6833f1049` passed 7/7. All recorded normal teardown.
- WebKit `3bebb484888a4c37bcb151bcaf5e7250` failed all seven cases before
  browser launch because this host lacked libmanette. Local Ubuntu packages
  libmanette and libhidapi were extracted into a private temporary directory
  and the owned Playwright browser cache; native WebKit launch then succeeded.
  No project dependency/config or system package was changed for this workaround.
- WebKit `b3626aac53b7471c87f04443a18db7f8` passed the guest journey and
  failed six actor setups on competing login navigations. Removing the fixture
  navigation alone in `797390cf8eec49c1ab46a6aad2b3b229` still left actors
  redirecting back to login. Authentication setup now starts at the public
  landing page, following Clerk's documented Playwright example, so the login
  form cannot independently navigate while the native helper activates a session.
  The resulting browser runs are pending; these failures remain failures.
- Removed all stopped-run temporary Next builds and tsconfig files, including
  interrupted-run outputs; preserved private reports and exact identity ledgers.
  Reconciled the two older ledgers that still had five undeleted identities each.
- Added automatic build/config removal through Playwright's reporter completion
  lifecycle, after its webServer stops; global teardown is too early for this.
  Cleanup never removes ordinary development .next or private diagnostics.
  The finite support check proves valid owned-path deletion, idempotence and
  traversal rejection. Support checks pass 16/16; root typecheck and focused
  lint pass. Actual failed WebKit runs also left zero temporary build/config files.

- The public-page helper experiment also failed six actor setups in WebKit
  (`c083560a510d40fb9193ec4779d5d343`). Switching actor setup to the existing
  real custom-form helper removed ticket/legacy-client setup and duplicate auth
  logic, but WebKit still returned to login. Investigation of the actual installed
  testing SDK revealed that its route handler follows the handshake redirect to
  HTML and calls response.json(), producing six recorded JSON syntax errors.
  The handshake now continues through the real browser network rather than that
  JSON-only testing handler; no Clerk or Pycil successful response is fabricated.
  This change alone has not yet produced a passing WebKit run.

- Finite private cookie diagnostics (`3c2f131a702b414e9cd68e7851c8697d`)
  confirmed an active Clerk client/session and localhost session cookies, but no
  client-UAT cookie; server auth consequently redirected back to login. The
  diagnostic instrumentation was removed after recording metadata without values.
  Clerk's current getSecureAttribute source documents Safari's HTTP-localhost
  Secure-cookie limitation. No browser cookie/security policy is disabled.
- E2E now uses local HTTPS with the same Caddy image as deployment. Playwright's
  native webServer lifecycle owns a run-labelled, automatically removed Caddy
  container, then production next build/start. TLS listeners use 3200/8100 and
  loopback upstreams use 3201/8101. CORS permits the actual HTTPS frontend origin.
  Browser/API test contexts accept only the local test certificate; SSR uses the
  internal HTTP endpoint. No Node global TLS override or Next API proxy is added.
  Caddy's native config validation and root TypeScript checks pass. Focused/full
  WebKit and subsequent Chromium/live/mobile/independent verification are pending.


### Cleanup delivery and debugging handoff

The cleanup-only delivery supersedes the earlier pending verification notes above.
Root-level `tsconfig.e2e.*.json` generation has been removed. All temporary Next
build/config/cache files now live in `apps/web/.e2e/<run-id>/`. Cleanup restores
Next's generated root declarations, preserving declarations changed by another
process. Cleanup tests use OS temporary directories and cannot leave fixtures in
`apps/web`. Legacy generated config/build leftovers have been removed.

Validation: 18/18 support checks; E2E package TypeScript check; native Next typegen
with the isolated config, frontend TypeScript check and exact declaration
restoration. No full browser suite was rerun during this bounded cleanup delivery.
The latest focused HTTPS WebKit run failed authentication, so current source is
not certified green. Historical default/live/mobile passes remain historical.
See [the detailed handoff](plans/reports/e2e-handoff.md) for evidence, reproduction,
current experimental configuration and the unproven redirect-race hypothesis.
No commit or push was performed in this cleanup delivery.
