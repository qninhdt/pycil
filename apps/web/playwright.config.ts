import { defineConfig, devices } from "@playwright/test"

/**
 * Browser journeys against a running Pycil stack.
 *
 * Playwright starts the Next.js app itself, on a fixed port, because Phase 14's
 * topology is web-outside-Docker: the deployed web app is a Vercel build, and the
 * local harness should mirror that rather than run a web container. A fixed port is
 * deliberate — an OS-assigned one would leave a developer unable to open the app a
 * failing journey was looking at, and a second run would collide with a stale server
 * they could not identify.
 *
 * The *backend* is not started from here. These specs need the real API, worker,
 * PostgreSQL, Redis and the reference dataset, and starting five services from a test
 * config hides their failures inside Playwright's output. `E2E_API_ORIGIN` names where
 * that stack is; its logs are read separately.
 *
 * `ignoreHTTPSErrors` is on because a local stack may terminate TLS at Caddy with a
 * self-signed certificate. That is a property of the local edge, not a relaxation the
 * deployed app relies on.
 */

/** The port the local web server is served on. Fixed so a failure is inspectable. */
const WEB_PORT = Number(process.env["E2E_WEB_PORT"] ?? 3100)

/** Where the API the browser talks to lives. */
const apiOrigin = process.env["E2E_API_ORIGIN"] ?? "https://localhost"

export default defineConfig({
  testDir: "./tests/e2e/specs",
  fullyParallel: false,
  // Serial: the journeys share one account and one stack, and a parallel run would
  // make their seeds race rather than make them faster.
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // `start` serves the production build, which is what Vercel deploys. A dev server
    // would exercise a different bundle — unminified, with its own error overlay — so
    // a journey could pass locally against something the deployment never runs.
    command: `pnpm exec next start --port ${WEB_PORT}`,
    url: `http://127.0.0.1:${WEB_PORT}`,
    reuseExistingServer: !process.env["CI"],
    timeout: 120_000,
    env: {
      // Server-side only. `NEXT_PUBLIC_*` is inlined into the bundle at build time, so
      // it cannot be set here — a journey that needs a different browser-visible API
      // origin must build with it, which is what `E2E_API_ORIGIN` documents rather
      // than papers over.
      PYCIL_API_URL: `${apiOrigin}/v1`,
    },
  },
})
