import 'server-only'

import { cache } from 'react'
import { getServerScope, getServerServices } from '@/lib/api/services/server'

export const loadServerAccount = cache(async () => {
  const [services, scope] = await Promise.all([getServerServices(), getServerScope()])
  if (scope === 'signed-out') return null
  return services.account.profile(new AbortController().signal)
})
