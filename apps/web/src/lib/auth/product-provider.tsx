import 'server-only'

import { authConfigured } from './config'
import { GuestServices, SessionProvider } from './session-provider.client'
import { loadServerAccount } from '@/lib/auth/account'
import { getServerScope } from '@/lib/api/services/server'
import { dataMode } from '@/lib/api/services/config'
import { PreviewProvider } from '@/lib/api/services/preview-provider.client'
import { getLocale, getMessages } from 'next-intl/server'

export async function ProductProvider({ children }: { children: React.ReactNode }) {
  if (dataMode === 'mock') return <PreviewProvider locale={await getLocale()} messages={await getMessages()}>{children}</PreviewProvider>
  if (!authConfigured) return <GuestServices>{children}</GuestServices>
  const [initialAccount, initialScope] = await Promise.all([loadServerAccount(), getServerScope()])
  return <SessionProvider initialAccount={initialAccount} initialScope={initialScope}>{children}</SessionProvider>
}
