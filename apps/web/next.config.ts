import type { NextConfig } from 'next'
import { loadEnvConfig } from '@next/env'
import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'
import { resolveDataMode } from './src/lib/services/config'

// Existing monorepo credentials stay server-only. Next exposes only NEXT_PUBLIC_*.
loadEnvConfig(fileURLToPath(new URL('../../', import.meta.url)))
const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  ?? process.env.CLERK_PUBLISHABLE_KEY ?? ''
const apiUrl = process.env.PYCIL_API_URL || 'http://127.0.0.1:8000'
const mode = resolveDataMode(process.env.NEXT_PUBLIC_DATA_MODE)

const config: NextConfig = {
  allowedDevOrigins: Object.values(networkInterfaces()).flatMap(interfaces =>
    interfaces?.filter(address => address.family === 'IPv4').map(address => address.address) ?? []),
  env: { NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: publishableKey, NEXT_PUBLIC_DATA_MODE: mode },
  turbopack: { root: fileURLToPath(new URL('./', import.meta.url)) },
  async rewrites() {
    if (mode === 'mock') return []
    return [{ source: '/api/v1/:path*', destination: `${apiUrl.replace(/\/$/, '')}/v1/:path*` }]
  },
}
export default config
