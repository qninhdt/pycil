import { cache } from 'react'
import { auth } from '@clerk/nextjs/server'
import { dataMode } from './config'
import { createMockServices } from './mock'
import { createHttpServices } from './http'
import type { FrontendServices } from './contracts'

/**
 * Server-safe singleton services provider.
 * Uses React 19 cache() to memoize per-request execution during SSR / RSC rendering.
 * Gracefully handles unauthenticated requests for public/guest browsing.
 */
export const getServerServices = cache(async (): Promise<FrontendServices> => {
  if (dataMode === 'mock') {
    return createMockServices()
  }

  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (!publishableKey) {
    return createHttpServices(async () => null)
  }

  try {
    const { getToken, userId } = await auth()
    if (!userId) {
      return createHttpServices(async () => null)
    }
    return createHttpServices(async () => {
      try {
        return await getToken()
      } catch {
        return null
      }
    })
  } catch (err) {
    if (
      typeof err === 'object' &&
      err !== null &&
      'digest' in err &&
      typeof (err as { digest?: string }).digest === 'string' &&
      (err as { digest: string }).digest.startsWith('DYNAMIC_SERVER_USAGE')
    ) {
      throw err
    }
    return createHttpServices(async () => null)
  }
})
