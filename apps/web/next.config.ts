import type { NextConfig } from 'next'
import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'
import createNextIntlPlugin from 'next-intl/plugin'
import { resolveDataMode } from './src/lib/services/config'

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts')

const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''
const apiUrl = process.env.PYCIL_API_URL || 'http://127.0.0.1:8000'
const mode = resolveDataMode(process.env.NEXT_PUBLIC_DATA_MODE)

const config: NextConfig = {
  allowedDevOrigins: Object.values(networkInterfaces()).flatMap(interfaces =>
    interfaces?.filter(address => address.family === 'IPv4').map(address => address.address) ?? []
  ),
  env: {
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: publishableKey,
    NEXT_PUBLIC_DATA_MODE: mode,
    NEXT_PUBLIC_PYCIL_API_URL: process.env.NEXT_PUBLIC_PYCIL_API_URL || apiUrl,
  },
  turbopack: { root: fileURLToPath(new URL('./', import.meta.url)) },
  experimental: { proxyTimeout: 210_000 },
}

export default withNextIntl(config)
