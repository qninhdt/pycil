import { auth, currentUser } from '@clerk/nextjs/server'
import { dataMode, getApiBaseUrl } from '@/lib/services/config'
import type { AccountProfile } from '@/lib/api'

export async function loadServerAccount(): Promise<AccountProfile | null> {
  if (dataMode === 'mock') return null
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (!publishableKey) return null

  try {
    const { getToken, userId } = await auth()
    if (!userId) return null
    const token = await getToken()
    if (!token) return null

    const res = await fetch(`${getApiBaseUrl()}/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    if (!res.ok) return null
    const profile = (await res.json()) as AccountProfile
    if (!profile.display_name) {
      try {
        const clerkUser = await currentUser()
        const resolvedName =
          clerkUser?.fullName ||
          clerkUser?.firstName ||
          clerkUser?.primaryEmailAddress?.emailAddress ||
          null
        if (resolvedName) {
          profile.display_name = resolvedName
        }
      } catch {
        // Fallback to profile as-is
      }
    }
    return profile
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
    console.error('[loadServerAccount] error:', err)
    return null
  }
}
