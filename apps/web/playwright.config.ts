import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_WEB_PORT ?? 3000);
const BASE_URL = process.env.BASE_URL ?? `http://localhost:${PORT}`;

// Web env threaded into the host `next start`/`next dev`. Real Dex login means
// the host web now performs the OIDC discovery + token exchange AND calls core's
// /auth/upsert-user on first login — neither of which the old minted-cookie
// fixture exercised. PYCIL_CORE_INTERNAL_URL defaults to the docker name
// `pycil-core:8000`, which the HOST cannot resolve; point it at the published
// loopback port so server-side upsertUser reaches core. OIDC_*/AUTH_URL must
// match the running Dex + the web port for the issuer/callback to line up.
const webEnv: Record<string, string> = {
  NEXT_PUBLIC_USE_MOCK: "false",
  E2E_PROXY: process.env["E2E_PROXY"] ?? "true",
  AUTH_URL: process.env.AUTH_URL ?? BASE_URL,
  PYCIL_CORE_INTERNAL_URL:
    process.env.PYCIL_CORE_INTERNAL_URL ?? "http://localhost:8000",
  NEXT_DEV_PROXY_TARGET:
    process.env.NEXT_DEV_PROXY_TARGET ?? "http://localhost:8000",
  OIDC_ISSUER_URL: process.env.OIDC_ISSUER_URL ?? "http://localhost:5556/dex",
  OIDC_CLIENT_ID: process.env.OIDC_CLIENT_ID ?? "pycil-web",
  OIDC_CLIENT_SECRET:
    process.env.OIDC_CLIENT_SECRET ?? "pycil-dex-secret-local-only",
  OIDC_PROVIDER_ID: process.env.OIDC_PROVIDER_ID ?? "oidc",
  OIDC_PROVIDER_NAME: process.env.OIDC_PROVIDER_NAME ?? "Dex",
};
// Auth.js signs/verifies the session JWT with AUTH_JWT_SECRET; only forward it
// when set so we never inject an empty secret that breaks token decode.
for (const k of ["AUTH_SECRET", "AUTH_JWT_SECRET", "INTERNAL_API_SECRET"]) {
  if (process.env[k]) webEnv[k] = process.env[k] as string;
}

export default defineConfig({
  testDir: "./e2e/tests",
  snapshotDir: "./e2e/snapshots",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report" }],
    ["junit", { outputFile: "test-results/e2e-junit.xml" }],
  ],
  outputDir: "test-results",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    // One real Dex login per run → saved storageState reused by every spec that
    // takes `authenticatedPage()` without an explicit user. Keeps the suite to a
    // single login (faster + gentler on Dex) while staying fully zero-mock.
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
  ],
  webServer: {
    // Default to a production build (next build && next start): the dev server's
    // on-demand Turbopack compile fires a Fast-Refresh remount the first time a
    // route's client chunk loads, which resets in-flight useState (e.g. the
    // learn session's sessionId) and silently breaks multi-step flows. A prod
    // build has no HMR, matches CI, and is what real users hit. Verified safe for
    // real Dex login: Chromium stores the __Secure- session cookie over
    // http://localhost (localhost is a trustworthy origin), so secure:true under
    // next start does not block login. Override with E2E_WEB_COMMAND for an
    // interactive dev loop.
    command:
      process.env.E2E_WEB_COMMAND ??
      `npx next build && npx next start -p ${PORT}`,
    port: PORT,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    env: webEnv,
  },
});
