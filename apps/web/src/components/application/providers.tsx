'use client'

import { createContext, useContext, useMemo, useState, useSyncExternalStore } from 'react'
import { ClerkProvider, useAuth, useSession, useUser } from '@clerk/react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import type { AccountProfile } from '@/lib/api'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { dataMode } from '@/lib/services/config'
import { createHttpServices } from '@/lib/services/http'
import { createMockServices } from '@/lib/services/mock'
import { ServicesProvider, useServices } from '@/lib/services/provider'

const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || ''
export const authConfigured = dataMode === 'live' && Boolean(publishableKey)
type Account = {
  status: 'loading' | 'signed-out' | 'ready' | 'error' | 'task'
  profile: AccountProfile | null
  name: string
  error: string | null
  signedIn: boolean
  retry: () => void
  signOut: () => Promise<void>
}
const AccountContext = createContext<Account>({
  status: 'signed-out', profile: null, name: 'Your account', error: null,
  signedIn: false, retry: () => {}, signOut: async () => {},
})
export const useAccount = () => useContext(AccountContext)

function subscribeTheme(callback: () => void) {
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  const storage = (event: StorageEvent) => {
    if (event.key === 'bauhaus-theme') document.documentElement.classList.toggle('dark', event.newValue === 'dark')
  }
  window.addEventListener('storage', storage)
  return () => { observer.disconnect(); window.removeEventListener('storage', storage) }
}
export function useTheme() {
  const theme = useSyncExternalStore<'light' | 'dark'>(subscribeTheme,
    () => document.documentElement.classList.contains('dark') ? 'dark' : 'light', () => 'light')
  return { theme, toggleTheme: () => {
    const next = theme === 'light' ? 'dark' : 'light'
    document.documentElement.classList.toggle('dark', next === 'dark')
    try { localStorage.setItem('bauhaus-theme', next) } catch { /* Storage is optional. */ }
  } }
}

function AccountProfileProvider({ state, fallbackName = 'Your account', signOut, children }: {
  state: 'loading' | 'signed-out' | 'authenticated' | 'task'; fallbackName?: string; signOut: () => Promise<void>; children: React.ReactNode
}) {
  const { services, scope } = useServices()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: [services.mode, scope, 'account'], queryFn: ({ signal }) => services.account.profile(signal),
    enabled: state === 'authenticated', initialData: state === 'authenticated' ? services.account.initialProfile : undefined })
  const profile = state === 'authenticated' ? query.data ?? null : null
  const value: Account = {
    status: state !== 'authenticated' ? state : query.isError ? 'error' : query.isPending ? 'loading' : 'ready',
    profile, name: profile?.display_name || fallbackName,
    error: state === 'authenticated' ? query.error?.message ?? null : null,
    signedIn: state === 'authenticated' || state === 'task',
    retry: () => { void query.refetch() },
    signOut: async () => { await queryClient.cancelQueries(); await signOut(); queryClient.clear() },
  }
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}

function AccountProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, sessionId, getToken, signOut } = useAuth()
  const { session } = useSession()
  const { user } = useUser()
  const services = useMemo(() => createHttpServices(getToken), [getToken])
  const scope = sessionId ?? 'signed-out'
  return <ServicesProvider key={`live:${scope}`} services={services} scope={scope}>
    <AccountProfileProvider state={!isLoaded ? 'loading' : !isSignedIn ? 'signed-out' : session?.currentTask ? 'task' : 'authenticated'}
      fallbackName={user?.fullName || user?.primaryEmailAddress?.emailAddress || 'Your account'} signOut={() => signOut({ redirectUrl: '/login' })}>{children}</AccountProfileProvider>
  </ServicesProvider>
}

function PreviewProvider({ children }: { children: React.ReactNode }) {
  const [services] = useState(() => createMockServices())
  const [signedOut, setSignedOut] = useState(false)
  const scope = signedOut ? 'signed-out' : services.account.initialProfile!.id
  return <ServicesProvider key={`mock:${scope}`} services={services} scope={scope}>
    <AccountProfileProvider state={signedOut ? 'signed-out' : 'authenticated'} signOut={async () => { setSignedOut(true) }}>{children}</AccountProfileProvider>
  </ServicesProvider>
}

const signedOutServices = createHttpServices(async () => null)

function ThemeToaster() {
  const { theme } = useTheme()
  return <Toaster theme={theme} position="bottom-right" />
}
export function Providers({ children }: { children: React.ReactNode }) {
  const contents = <TooltipProvider>{children}<ThemeToaster /></TooltipProvider>
  if (dataMode === 'mock') return <PreviewProvider>{contents}</PreviewProvider>
  return authConfigured ? <ClerkProvider publishableKey={publishableKey} signInUrl="/login" signUpUrl="/signup"
    signInFallbackRedirectUrl="/app" signUpFallbackRedirectUrl="/app" afterSignOutUrl="/login">
    <AccountProvider>{contents}</AccountProvider>
  </ClerkProvider> : <ServicesProvider services={signedOutServices} scope="signed-out">{contents}</ServicesProvider>
}
