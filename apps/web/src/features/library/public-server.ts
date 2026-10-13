import 'server-only'

import { cache } from 'react'
import { notFound } from 'next/navigation'
import { ApiError } from '@/lib/api/error'
import { getServerServices } from '@/lib/api/services/server'

export const publicProfile = cache(async (identifier: string) => {
  try { return await (await getServerServices()).account.publicProfile(identifier, new AbortController().signal) }
  catch (error) { if (error instanceof ApiError && [403, 404].includes(error.status)) {
      if ((await getServerServices()).mode === 'mock') return null
      notFound()
    } throw error }
})
export const publicNode = cache(async (identifier: string, nodeId: string) => {
  const profile = await publicProfile(identifier)
  try {
    const node = await (await getServerServices()).library.publicNode(nodeId, new AbortController().signal)
    if (profile && node.owner_id !== profile.id) notFound()
    return node
  } catch (error) { if (error instanceof ApiError && [403, 404].includes(error.status)) {
      if ((await getServerServices()).mode === 'mock') return null
      notFound()
    } throw error }
})
