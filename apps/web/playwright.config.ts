import { defineConfig, devices } from "@playwright/test"

/**
 * The browser layer: real Chromium/WebKit against the real `docker compose` stack.
 *
 * This config deliberately does NOT start the app. The suite asserts things that
 * only exist in the full stack — an SSE verdict arriving over Centrifugo, a
 * pending grade surviving a reload, a recap read back from the durable summary —
 * so a `webServer` block running `next dev` would quietly test a different system
 * than the one being shipped. `global-setup.ts` fails with an actionable message
 * when the stack is not up, rather than letting every spec time out separately.
 *
 * Run it with:
 *
 * ```
 * docker compose up -d --build
 * pnpm --filter web test:e2e
 * ```
 */

/**
 * One origin for the browser, the API, and SSE.
 *
 * The app, `/v1`, and `/connection/sse` share a single Caddy origin
 * specifically so the SSE URL the API hands the browser is same-origin: a
 * frontend on its own port would make every subscribe cross-origin and would
 * have to be added to `CENTRIFUGO_ALLOWED_ORIGINS`. Pointing the suite anywhere
 * else would make the realtime specs fail for infrastructure reasons rather than
 * on the application.
 */
const baseURL = process.env.E2E_BASE_URL || "https://localhost"

/**
 * Caddy issues the local certificate from its own CA, which no browser trusts.
 * That is a property of local TLS, not of the app, so it is accepted here rather
 * than worked around by dropping to HTTP — the session cookie is `secure`, so
 * over plain HTTP it would never be sent and every authenticated spec would fail
 * as a redirect to `/login`.
 */
const ignoreHTTPSErrors = true

export default defineConfig({
  testDir: "./tests/e2e/specs",
  /**
   * Serial, and not as a concession to flakiness.
   *
   * Three things in this system are shared per user and would make parallel specs
   * interfere for real: the grading quota is a per-user Redis budget, the
   * generation slot budget is per user, and `/next` mutates session state. A
   * quota-exhaustion spec running beside the study loop would drain the budget
   * the other one depends on, and the failure would land in whichever spec lost
   * the race. Each spec still seeds its own folder and deck, so the isolation is
   * belt and braces rather than either alone.
   */
  fullyParallel: false,
  workers: 1,
  /**
   * No retries. A retry on this suite would hide exactly the bugs it exists to
   * find: the async paths here are meant to converge, and a spec that only passes
   * on the second attempt is reporting a real defect in recovery.
   */
  retries: 0,
  forbidOnly: !!process.env.CI,
  /**
   * Generous, because the honest floor is set by a language model. Question
   * supply is prepared asynchronously and graded by a judge, so a free-text
   * verdict legitimately takes tens of seconds. Individual waits are tighter;
   * this is the outer bound before a spec is declared hung.
   */
  timeout: 180_000,
  expect: { timeout: 20_000 },
  globalSetup: "./tests/e2e/global-setup.ts",
  reporter: process.env.CI
    ? [["github"], ["html", { outputFolder: "playwright-report", open: "never" }], ["json", { outputFile: "playwright-report/results.json" }]]
    : [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL,
    ignoreHTTPSErrors,
    /** Evidence for a failure, and nothing retained for a pass. */
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    /** The sealed cookie written by `global-setup`. */
    storageState: "./tests/e2e/.auth/state.json",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    /**
     * WebKit and Mobile Safari are not redundant with Chromium here. `100dvh`,
     * safe-area insets, and the sticky-footer behaviour the study loop depends on
     * are iOS problems first, and a desktop-Chromium-only suite would ship them
     * broken.
     */
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile-safari",
      use: { ...devices["iPhone 14"] },
    },
    /**
     * The review screenshot set, deliberately not part of the gating suite.
     *
     * Its own project rather than a spec, because it must be excluded from a plain
     * `playwright test` run: it captures every screen at two viewports in both
     * themes, which is minutes of work that asserts almost nothing. `testDir`
     * points outside `tests/e2e/specs` so the default projects never pick it up,
     * and the global setup is shared so it captures the same seeded fixture the
     * suite runs against.
     */
    {
      name: "screenshots",
      testDir: "./tests/screenshots",
      // `capture.ts` is not a `*.spec.ts`, deliberately: the default `testMatch` is
      // what keeps a plain `playwright test` from picking it up, and naming it as a
      // spec would put a minutes-long capture run inside the gating suite.
      testMatch: /capture\.ts$/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
})
