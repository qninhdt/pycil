import type { Metadata } from 'next'
import { Providers } from '@/components/application/providers'
import { initialUiScript } from '@/lib/ui-preferences'
import './globals.css'

import { auth, currentUser } from '@clerk/nextjs/server'
import { dataMode } from '@/lib/services/config'
import type { AccountProfile } from '@/lib/api'

export const metadata: Metadata = {
  title: { default: 'Pycil', template: '%s — Pycil' },
  description: 'Organize the meanings you want to learn. Practice, review, and return at your own pace.',
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon.ico', sizes: '32x32' },
    ],
    apple: '/apple-touch-icon.png',
  },
}

async function loadServerAccount(): Promise<AccountProfile | null> {
  if (dataMode === 'mock') return null
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (!publishableKey) return null

  try {
    const { getToken, userId } = await auth()
    if (!userId) return null
    const token = await getToken()
    if (!token) return null

    const apiUrl = process.env.PYCIL_API_URL || 'http://127.0.0.1:8000'
    const res = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/me`, {
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
    console.error('[loadServerAccount] error:', err)
    return null
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const initialAccount = await loadServerAccount()
  return <html lang="en" data-scroll-behavior="smooth" data-time-of-day="morning" data-navigation-collapsed="false" suppressHydrationWarning>
    <head>
      <link id="app-icon" rel="icon" href="/favicon.svg" type="image/svg+xml" />
      <link rel="alternate icon" href="/favicon.ico" />
      <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      <script dangerouslySetInnerHTML={{ __html: initialUiScript }} />
    </head>
    <body><Providers initialAccount={initialAccount}>{children}</Providers></body>
  </html>
}
