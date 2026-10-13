'use client'

import { createContext, useContext, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { ClerkProvider, useAuth, useSession, useUser } from '@clerk/nextjs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import type { AccountProfile } from '@/lib/api'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { dataMode } from '@/lib/services/config'
import { createHttpServices } from '@/lib/services/http'
import { createMockServices } from '@/lib/services/mock'
import { ServicesProvider, useServices } from '@/lib/services/provider'
import { I18nProvider } from './i18n-provider'

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

const ACCOUNT_CACHE_KEY = 'pycil-account-cache'
const subscribeHydration = () => () => {}
function getCachedAccount(): { name: string; plan?: string } | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(ACCOUNT_CACHE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}
function setCachedAccount(data: { name: string; plan?: string }) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(ACCOUNT_CACHE_KEY, JSON.stringify(data))
  } catch {
    // Storage is optional.
  }
}

function AccountProfileProvider({ state, fallbackName = 'Your account', signOut, initialProfile, children }: {
  state: 'loading' | 'signed-out' | 'authenticated' | 'task'; fallbackName?: string; signOut: () => Promise<void>; initialProfile?: AccountProfile | null; children: React.ReactNode
}) {
  const { services, scope } = useServices()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: [services.mode, scope, 'account'], queryFn: ({ signal }) => services.account.profile(signal),
    enabled: state === 'authenticated', initialData: state === 'authenticated' ? (initialProfile ?? services.account.initialProfile) : undefined })
  const profile = state === 'authenticated' ? query.data ?? initialProfile ?? null : null

  useEffect(() => {
    if (profile?.display_name) {
      setCachedAccount({ name: profile.display_name, plan: profile.plan })
    } else if (fallbackName && fallbackName !== 'Your account') {
      setCachedAccount({ name: fallbackName, plan: profile?.plan })
    }
  }, [profile?.display_name, profile?.plan, fallbackName])

  const value: Account = {
    status: state !== 'authenticated' ? state : query.isError ? 'error' : query.isPending && !profile ? 'loading' : 'ready',
    profile, name: profile?.display_name || fallbackName,
    error: state === 'authenticated' ? query.error?.message ?? null : null,
    signedIn: state === 'authenticated' || state === 'task',
    retry: () => { void query.refetch() },
    signOut: async () => {
      try { localStorage.removeItem(ACCOUNT_CACHE_KEY) } catch { /* Optional. */ }
      await queryClient.cancelQueries()
      queryClient.clear()
      await signOut()
    },
  }
  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>
}

function AccountProvider({ initialAccount, children }: { initialAccount?: AccountProfile | null; children: React.ReactNode }) {
  const hydrated = useSyncExternalStore(subscribeHydration, () => true, () => false)
  const { isLoaded, isSignedIn, sessionId, getToken, signOut } = useAuth()
  const { isLoaded: sessionLoaded, session } = useSession()
  const { user } = useUser()
  const services = useMemo(() => createHttpServices(getToken), [getToken])
  const scope = sessionId ?? 'signed-out'
  const cached = useMemo(() => getCachedAccount(), [])
  const state = !hydrated || !isLoaded || !sessionLoaded
    ? 'loading'
    : session?.currentTask
      ? 'task'
      : !isSignedIn
        ? 'signed-out'
        : 'authenticated'
  const fallbackName = initialAccount?.display_name || (hydrated ? user?.fullName || user?.primaryEmailAddress?.emailAddress || cached?.name : null) || 'Your account'

  return <ServicesProvider key={`live:${scope}`} services={services} scope={scope}>
    <AccountProfileProvider
      state={state}
      initialProfile={initialAccount}
      fallbackName={fallbackName}
      signOut={() => signOut({ redirectUrl: '/login' })}
    >
      {children}
    </AccountProfileProvider>
  </ServicesProvider>
}

export function PreviewProvider({ children }: { children: React.ReactNode }) {
  const [services] = useState(() => createMockServices())
  const [signedOut, setSignedOut] = useState(false)
  const scope = signedOut ? 'signed-out' : services.account.initialProfile!.id
  return (
    <I18nProvider>
      <ServicesProvider key={`mock:${scope}`} services={services} scope={scope}>
        <AccountProfileProvider state={signedOut ? 'signed-out' : 'authenticated'} signOut={async () => { setSignedOut(true) }}>{children}</AccountProfileProvider>
      </ServicesProvider>
    </I18nProvider>
  )
}

const signedOutServices = createHttpServices(async () => null)

function ThemeToaster() {
  const { theme } = useTheme()
  return <Toaster theme={theme} position="bottom-right" />
}
export function Providers({ initialAccount, children }: { initialAccount?: AccountProfile | null; children: React.ReactNode }) {
  const contents = <I18nProvider><TooltipProvider>{children}<ThemeToaster /></TooltipProvider></I18nProvider>
  if (dataMode === 'mock') return <PreviewProvider>{contents}</PreviewProvider>
  return authConfigured ? <ClerkProvider publishableKey={publishableKey} signInUrl="/login" signUpUrl="/signup"
    signInFallbackRedirectUrl="/app" signUpFallbackRedirectUrl="/app" afterSignOutUrl="/login">
    <AccountProvider initialAccount={initialAccount}>{contents}</AccountProvider>
  </ClerkProvider> : <ServicesProvider services={signedOutServices} scope="signed-out">{contents}</ServicesProvider>
}
