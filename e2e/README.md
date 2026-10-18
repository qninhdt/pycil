# Product E2E

The root package owns production-stack public, authentication, account, Library,
vocabulary, Study, Assistant and rendering journeys. Frontend unit/browser
integration and backend unit/integration retain their separate owners.
See [the execution plan and handoff](../plans/reports/e2e-handoff.md) for the full coverage and cutover criteria.

## Prerequisites

- Node 24, pnpm 12, Docker Engine with Compose v2.
- Install web dependencies: `pnpm --dir apps/web install --frozen-lockfile`.
- Install E2E dependencies: `pnpm --dir e2e install --frozen-lockfile`.
- Install Chromium: `pnpm --dir e2e exec playwright install chromium`.
- Copy `e2e/.env.example` to `e2e/.env` and supply development Clerk credentials.
  CI supplies the same variables through its environment. An explicitly selected
  alternate file can be passed with `E2E_ENV_FILE`; application dotenv files are
  never searched by this package. Environment variables take precedence.

`pnpm --dir e2e test` runs the controlled-model profile with a production frontend,
real identity, and disposable backend stores. Ports 3200, 8100, and 8110 must be
free. Development servers on 3000/8000 and browser integration on 3100 are separate.
The production Next server listens on loopback 3200, and the API listens on loopback 8100.
Browser requests reach Pycil directly, with no Next API proxy.
The `live`, `mobile`, `webkit`, and `external-auth` commands select distinct
projects. Live has a fixed generation/grading/Assistant scope. External auth
requires enabled development TOTP (`E2E_TOTP_ENABLED=true`) and a dedicated
Google identity (`E2E_GOOGLE_EMAIL` / `E2E_GOOGLE_PASSWORD`). Missing prerequisites
fail selected external coverage. A profile with no tests is an error, not coverage.

## Boundaries

Tests use public HTTP APIs for setup and persistence checks; the target action is
performed through the browser. They do not import frontend parsers or inspect the
Study session to find correct answers. Ordinary provider scenarios control only
external protocols; unmatched model requests fail. Container startup uses the
production API Dockerfile and genuine migration/reference/checkpoint gates.
The disposable stack runs API and native Taskiq worker services from that same
image. The worker consumes preparation/generation jobs from the stack's Redis;
it receives database, Redis and model-provider configuration, with no Clerk
credentials or published HTTP port. Its command is owned by
[`support/compose.yaml`](support/compose.yaml).

`pnpm --dir e2e typecheck` checks this package. `pnpm --dir e2e test:support`
checks provider/identity recovery boundaries without external services or containers. Test collection
(`pnpm --dir e2e exec playwright test --project=default --list`) creates no
containers, identities, or frontend processes.

## Ownership and diagnostics

Each test user has a fresh Clerk identity and session. Ordinary setup activates
a real Clerk ticket session and navigates directly through `/auth/complete`;
authentication journeys exercise the real custom sign-in/verification form. The
native Clerk testing helper handles its JSON endpoints; the handshake redirect continues through
the actual browser network because it can legitimately return HTML. Exact owned emails/IDs are
recorded in an ignored private run ledger; normal global teardown reconciles
identities and removes the owned Compose project and volumes. Baseline lexical
fixtures are seeded before API search startup. Genuine source reference IDs remain
unchanged in the small JSONL fixture.

If Clerk user creation loses its HTTP response, setup checks the reserved email
before one bounded retry. It reuses a user that was already created, reports the
recovery, and never retries validation failures or whole tests. A second transport
failure fails setup. Deleting an owned identity likewise retries one lost
transport response and accepts 404 as already deleted; other errors still fail
cleanup. Clerk failures retain status/error codes without publishing
provider messages or metadata.

Ignored `.artifacts/<run-id>/` contains private HTML/JSON reports, logs and runtime metadata.
Trace/screenshots are disabled until a private artifact policy is configured.
Never publish raw Clerk/browser/provider logs or commit `.env`/auth state. Abrupt
host death can prevent remote identity cleanup; retain the exact ledger for
recovery rather than deleting users based on a broad prefix.

For an interrupted run, stop its frontend and run
`pnpm --dir e2e recover:identities <run-id>` with the same development credentials.
This reconciles only the exact identities in that run's ledger. It does not delete
unrelated users or manage another process's containers.

Next build output, TypeScript config/cache and the declarations backup are isolated
under `apps/web/.e2e/<run-id>/`; normal `.next` is preserved. No per-run config
files are written at the web project root. Next itself writes `next-env.d.ts` at
that root; cleanup restores its previous contents (or absence) when the file still
belongs to this run. A declaration file regenerated by another process is preserved. Do not delete a run's build files while its webServer is active.
Playwright automatically removes the run's build/config output after its webServer
stops, including failed tests and setup. Private diagnostics are retained. For old
runs left by an interrupted process, `pnpm --dir e2e run clean <run-id>` requires a
successful cleanup record and a stopped frontend before removing that run's output.

See [the E2E handoff](../plans/reports/e2e-handoff.md) for verified results and the
unresolved WebKit login failure. Earlier green runs do not validate later changes.
