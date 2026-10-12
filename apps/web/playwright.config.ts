import { defineConfig } from '@playwright/test'

const integrationURL = 'http://127.0.0.1:3100'
const liveProvider = process.env.E2E_PROVIDER_PROFILE === 'live'

export default defineConfig({
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results',
  use: {
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  webServer: process.env.E2E_BASE_URL ? undefined : {
    command: 'pnpm dev --port 3100',
    env: { NEXT_PUBLIC_DATA_MODE: 'mock', NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: '' },
    url: integrationURL, reuseExistingServer: false,
  },
  projects: [
    {
      name: 'integration', testDir: './tests/integration/browser', testMatch: '**/*.test.ts',
      use: { baseURL: integrationURL },
    },
    { name: 'auth-setup', testDir: './tests/e2e', testMatch: 'auth.setup.ts' },
    {
      name: 'e2e', testDir: './tests/e2e', testMatch: '**/*.test.ts', dependencies: ['auth-setup'],
      grep: liveProvider ? /@live-provider/ : undefined,
      grepInvert: liveProvider ? undefined : /@live-provider/,
      timeout: 60000, expect: { timeout: 15000 },
      use: {
        baseURL: process.env.E2E_BASE_URL, actionTimeout: 15000, navigationTimeout: 30000,
        // Auth traces contain bearer tokens and Clerk credentials.
        trace: 'off', screenshot: 'only-on-failure',
      },
    },
  ],
})
