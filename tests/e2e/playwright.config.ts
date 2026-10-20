import { defineConfig, devices } from '@playwright/test'
import { artifacts, credentials, frontendEnvironment, root, webURL } from './support/environment.ts'

const selected = process.argv.flatMap((argument, index) => argument.startsWith('--project=') ? [argument.slice(10)] : argument === '--project' ? [process.argv[index + 1]] : [])
if (selected.length === 0 && process.env.E2E_SELECTED_PROJECT) selected.push(process.env.E2E_SELECTED_PROJECT)
const collecting = process.argv.some(argument => ['--list', '--help', '-h'].includes(argument))
if (!collecting && (selected.length !== 1 || !['default', 'live', 'mobile', 'webkit', 'external-auth'].includes(selected[0]))) {
  throw new Error('Select exactly one explicit E2E project: default, live, mobile, webkit, or external-auth')
}
const live = selected.includes('live')
if (selected.length === 1) process.env.E2E_SELECTED_PROJECT = selected[0]
if (!collecting) credentials(live)
process.env.E2E_PROVIDER_PROFILE = live ? 'live' : 'default'

const critical = ['**/vocabulary/dictionary.test.ts', '**/library/editing.test.ts', '**/study/session.test.ts']
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  workers: 2,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  globalSetup: './global-setup.ts',
  outputDir: `${artifacts}/browser`,
  reporter: [...(collecting ? [] : [['./support/clean.ts'] as [string]]), ['list'], ['json', { outputFile: `${artifacts}/results.json` }], ['html', { outputFolder: `${artifacts}/report`, open: 'never' }]],
  use: {
    baseURL: webURL,
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  webServer: {
    command: `node --experimental-strip-types "${root}/tests/e2e/support/prepare-web.ts" && pnpm build > "$E2E_ARTIFACTS/web.log" 2>&1 && pnpm start --hostname localhost --port 3200 >> "$E2E_ARTIFACTS/web.log" 2>&1`,
    cwd: `${root}/apps/web`,
    env: frontendEnvironment(),
    url: `${webURL}/icon.svg`,
    ignoreHTTPSErrors: true,
    reuseExistingServer: false,
    timeout: 240_000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 15_000 },
    stdout: 'ignore',
    stderr: 'ignore',
  },
  projects: [
    { name: 'default', testIgnore: ['**/live/**', '**/external-auth/**'] },
    { name: 'live', testMatch: '**/live/*.test.ts', timeout: 180_000 },
    { name: 'mobile', testMatch: critical, use: { ...devices['Pixel 7'] } },
    { name: 'webkit', testMatch: critical, use: { browserName: 'webkit' } },
    { name: 'external-auth', testMatch: '**/external-auth/*.test.ts' },
  ],
})
