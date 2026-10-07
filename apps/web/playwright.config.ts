import { defineConfig } from '@playwright/test'

const port = process.env.PORT || '3000'
const baseURL = process.env.BASE_URL || `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  webServer: {
    command: `pnpm run dev --hostname 127.0.0.1 --port ${port}`,
    env: { NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: '', CLERK_SECRET_KEY: '' },
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
})
