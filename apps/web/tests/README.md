# Frontend tests

Run commands from `apps/web` after installing dependencies and Chromium.

| Command | Boundary |
| --- | --- |
| `pnpm test:unit` | Vitest: isolated functions, schemas, state transitions and static rendering |
| `pnpm test:integration` | Vitest HTTP/preview/assets contracts, then Playwright components/pages/browser behavior |
| `pnpm test:e2e` | Production frontend, actual Pycil backend, disposable PostgreSQL/Redis, actual Clerk; controlled LLM boundary |
| `pnpm test:e2e:live` | Selected `@live-provider` E2E with configured paid inference/decision services |
| `pnpm test` | All ordinary levels, excluding paid LLM checks |

Files use kebab-case `.test.ts` or `.test.tsx`, named for their subject. Tests live in
`unit/`, `integration/{services,assets,browser}/`, or `e2e/`. Fixture inputs and helpers
are ordinary modules, excluded from collection. Stories remain colocated preview
examples and are not counted as an additional assertion suite.

Integration browser tests can control authentication/context and HTTP responses.
Preview service tests verify the design preview's own contract; they do not prove
backend behavior. E2E actions run native validation/generation/grading/tool/persistence
paths. Only the LLM boundary is controlled in ordinary E2E; paid checks use the same
application code with real providers. Pure backend invariants belong in API integration.

For focused checks:

```sh
pnpm exec vitest run tests/unit/study-storage.test.ts --project unit
pnpm exec vitest run tests/integration/services/http-services.test.ts --project integration
pnpm exec playwright test assistant.test.ts --project=integration
E2E_GREP='Practice 390px' pnpm test:e2e
```

`playwright.config.ts` owns browser integration and E2E projects; `vitest.config.ts`
owns unit and service/assets integration. Each file is collected exactly once.
Integration uses owned port 3100. Managed E2E uses owned frontend 3200 and API 8100;
occupied ports fail rather than reusing another server. User dev on 3000 and API on
8000 remain separate. The runner uses a source snapshot for its production build.

E2E requires development `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_ISSUER`
and `CLERK_JWKS_URL`. It reads environment or root `.env`; the publishable key can
also come from `apps/web/.env.local`. `E2E_CLERK_ENV_FILE` selects another runner-only
file. Paid checks additionally require `INFERENCE_API_KEY`, `INFERENCE_BASE_URL`,
`LEXI_DECISION_API_KEY`, and `LEXI_DECISION_BASE_URL`. Credentials never appear in
browser fixtures, test source or reports. Google OAuth requires a dedicated test
identity; TOTP reports an explicit skip if the development instance disables it.

The existing `scripts/test_api.py` owns disposable stores. Backend test support owns
lexical data, inference fixtures, provisioning and process cleanup; the system test
is only the orchestration entry. Cleanup targets exact test users/nodes/processes and
Docker project IDs. No application database or broad Redis flush is used.

CI runs unit/integration/build on fork PRs. Trusted changes also require real-stack
E2E with development secrets; absence fails instead of silently passing. Manual
`live_provider` selects paid checks. A skipped fork E2E job is missing coverage,
not an E2E pass. Configure the four Clerk secrets in the repository before relying
on the trusted E2E job.

Reports in `test-results/` and `playwright-report/` are private, ignored artifacts.
Auth traces are disabled because they contain tokens. Screenshot output alone is
not visual regression evidence; assertions must check meaningful behavior/layout.
