# Frontend tests

Run commands from `apps/web` after installing dependencies and Chromium.

| Command | Boundary |
| --- | --- |
| `pnpm test:unit` | Vitest: isolated functions, schemas, state transitions and static rendering |
| `pnpm test:integration` | Vitest: HTTP/preview/assets contracts |
| `pnpm test:vitest` | Vitest: all unit and contract tests in one run |
| `pnpm test:browser` | Playwright: component/page/browser behavior |
| `pnpm test` | Both frontend-owned levels (`test:vitest && test:browser`) |

Files use kebab-case `.test.ts` or `.test.tsx`, named for their subject. Tests live in
`unit/` or `integration/{services,assets,browser}/`. Stories are colocated preview
examples. They are not another assertion suite.

Browser integration may control identity/context and HTTP responses to test UI
contracts and failure handling. Preview tests prove the preview's contract. They
do not prove production backend behavior. API-only invariants belong to backend
integration tests with real infrastructure.

`vitest.config.ts` owns unit and service/assets integration. `playwright.config.ts`
owns browser integration only, on port 3100. Its ignored reports are private
`test-results/browser/` and `playwright-report/`; screenshot output alone is not
visual regression evidence.

```sh
pnpm exec vitest run tests/unit/study-storage.test.ts --project unit
pnpm exec vitest run tests/integration/services/http-services.test.ts --project integration
pnpm exec playwright test assistant.test.ts --project=integration
```

Product browser E2E has its own root package, infrastructure, credentials, fixtures,
profiles and reports. See [Product E2E](../../../e2e/README.md) for default/live,
mobile/WebKit, external authentication and interrupted-run cleanup commands.
