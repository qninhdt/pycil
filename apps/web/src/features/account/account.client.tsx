'use client'

import { createContext, useContext } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { AccountProfile } from '@/lib/api/account'
import { useServices } from '@/lib/api/services/provider.client'

type Identity = {
  state: 'loading' | 'signed-out' | 'authenticated' | 'task'
  initialProfile?: AccountProfile | null
  sdkReady?: boolean
  signOut: () => Promise<void>
}
export const IdentityContext = createContext<Identity>({ state: 'signed-out', signOut: async () => {} })

export function useAccount() {
  const { state, initialProfile, sdkReady, signOut } = useContext(IdentityContext)
  const { services, scope } = useServices()
  const client = useQueryClient()
  const query = useQuery({ queryKey: [services.mode, scope, 'account'], queryFn: ({ signal }) => services.account.profile(signal),
    enabled: state === 'authenticated', initialData: state === 'authenticated' ? initialProfile ?? services.account.initialProfile : undefined })
  const profile = state === 'authenticated' ? query.data ?? null : null
  return {
    status: state !== 'authenticated' ? state : query.isError ? 'error' as const : query.isPending ? 'loading' as const : 'ready' as const,
    profile, name: profile?.display_name || 'Your account',
    error: state === 'authenticated' ? query.error?.message ?? null : null,
    canMutate: state === 'authenticated' && sdkReady !== false,
    signedIn: state === 'authenticated' || state === 'task',
    retry: () => { void query.refetch() },
    signOut: async () => { await client.cancelQueries(); client.clear(); await signOut() },
  }
}
