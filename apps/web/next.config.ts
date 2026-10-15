import type { NextConfig } from 'next'
import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'
import createNextIntlPlugin from 'next-intl/plugin'
import { localApiOrigin } from './src/config'
import { resolveDataMode } from './src/lib/api/services/config'

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts')

const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''
const mode = resolveDataMode(process.env.NEXT_PUBLIC_DATA_MODE)

const config: NextConfig = {
  distDir: process.env.E2E_RUN_ID ? `.e2e/${process.env.E2E_RUN_ID}/next` : '.next',
  typescript: { tsconfigPath: process.env.E2E_RUN_ID ? `.e2e/${process.env.E2E_RUN_ID}/tsconfig.json` : 'tsconfig.json' },
  allowedDevOrigins: Object.values(networkInterfaces()).flatMap(interfaces =>
    interfaces?.filter(address => address.family === 'IPv4').map(address => address.address) ?? []
  ),
  env: {
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: publishableKey,
    NEXT_PUBLIC_DATA_MODE: mode,
    NEXT_PUBLIC_PYCIL_API_URL: process.env.NEXT_PUBLIC_PYCIL_API_URL || localApiOrigin,
  },
  turbopack: { root: fileURLToPath(new URL('./', import.meta.url)) },
}

export default withNextIntl(config)
