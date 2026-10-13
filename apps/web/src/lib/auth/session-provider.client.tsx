'use client'

import { useMemo, useState } from 'react'
import { useAuth, useSession } from '@clerk/nextjs'
import type { AccountProfile } from '@/lib/api/account'
import { IdentityContext } from '@/features/account/account.client'
import { createHttpServices } from '@/lib/api/services/http'
import { ServicesProvider } from '@/lib/api/services/provider.client'

export function SessionProvider({ initialAccount, initialScope, children }: { initialAccount: AccountProfile | null; initialScope: string; children: React.ReactNode }) {
  const { isLoaded, sessionId, getToken, signOut } = useAuth()
  const { isLoaded: sessionLoaded, session } = useSession()
  const [signingOut, setSigningOut] = useState(false)
  const services = useMemo(() => createHttpServices(getToken), [getToken])
  const scope = signingOut ? 'signed-out' : isLoaded ? sessionId ?? 'signed-out' : initialScope
  const initialProfile = scope === initialScope ? initialAccount : null
  const state = signingOut ? 'signed-out' : session?.currentTask ? 'task' : !isLoaded || !sessionLoaded
    ? initialProfile ? 'authenticated' : initialScope === 'signed-out' ? 'signed-out' : 'loading'
    : sessionId ? 'authenticated' : 'signed-out'
  return <ServicesProvider services={services} scope={scope}>
    <IdentityContext.Provider value={{ state, initialProfile, sdkReady: isLoaded && sessionLoaded, signOut: async () => {
      setSigningOut(true)
      try { await signOut({ redirectUrl: '/login' }) }
      catch (error) { setSigningOut(false); throw error }
    } }}>{children}</IdentityContext.Provider>
  </ServicesProvider>
}

export function GuestServices({ children }: { children: React.ReactNode }) {
  const services = useMemo(() => createHttpServices(async () => null), [])
  return <ServicesProvider services={services} scope="signed-out">{children}</ServicesProvider>
}
