import { defineConfig } from '@playwright/test'

const integrationURL = 'http://127.0.0.1:3100'

export default defineConfig({
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 2,
  fullyParallel: false,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  outputDir: 'test-results/browser',
  use: {
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  webServer: {
    command: process.env.PLAYWRIGHT_USE_PROD ? 'pnpm start --port 3100' : 'pnpm dev --port 3100',
    env: { NEXT_PUBLIC_DATA_MODE: 'mock', NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: '' },
    url: integrationURL,
    reuseExistingServer: !process.env.CI,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
  },
  projects: [
    {
      name: 'integration', testDir: './tests/integration/browser', testMatch: '**/*.test.ts',
      use: { baseURL: integrationURL },
    },

  ],
})
