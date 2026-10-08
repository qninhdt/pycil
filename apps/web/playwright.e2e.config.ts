import { defineConfig } from '@playwright/test'

const baseURL = process.env.E2E_BASE_URL
if (!baseURL) throw new Error('Set E2E_BASE_URL to an already running live frontend backed by disposable test stores.')

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: [['list'], ['html', { outputFolder: 'e2e-report', open: 'never' }]],
  outputDir: 'e2e-results',
  projects: [
    { name: 'clerk-setup', testMatch: /clerk\.setup\.ts/ },
    { name: 'full-stack', testMatch: /.*\.spec\.ts/, dependencies: ['clerk-setup'] },
  ],
  use: {
    baseURL,
    actionTimeout: 15000,
    navigationTimeout: 30000,
    viewport: { width: 1440, height: 1000 },
    // Network traces include bearer tokens and Clerk credentials.
    trace: 'off',
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : undefined,
  },
})
