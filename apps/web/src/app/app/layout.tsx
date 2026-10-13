import { auth } from '@clerk/nextjs/server'
import { dataMode } from '@/lib/services/config'
import { loadServerAccount } from '@/lib/server-account'
import { AppAccountScope } from '@/components/application/app-account-scope'

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (dataMode !== 'mock' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    await auth.protect()
  }
  const initialAccount = await loadServerAccount()
  return <AppAccountScope initialAccount={initialAccount}>{children}</AppAccountScope>
}
