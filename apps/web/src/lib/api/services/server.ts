import 'server-only'

import { cache } from 'react'
import { auth } from '@clerk/nextjs/server'
import { dataMode } from './config'
import { createMockServices } from './mock'
import { createHttpServices } from './http'

export const getPublicServices = cache(() => dataMode === 'mock' ? createMockServices() : createHttpServices(async () => null))

export const getServerServices = cache(async () => {
  if (dataMode === 'mock') return createMockServices()
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) return createHttpServices(async () => null)
  const { getToken } = await auth()
  return createHttpServices(getToken)
})

export const getServerScope = cache(async (): Promise<string> => {
  if (dataMode === 'mock') return (await getServerServices()).account.initialProfile!.id
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) return 'signed-out'
  return (await auth()).sessionId ?? 'signed-out'
})
