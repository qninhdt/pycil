import { auth } from '@clerk/nextjs/server'
import { dataMode } from '@/lib/api/services/config'
import type { Metadata } from 'next'

export const metadata: Metadata = { robots: { index: false, follow: false } }

export default async function PrivateWorkspace({ children }: { children: React.ReactNode }) {
  if (dataMode !== 'mock' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) await auth.protect()
  return children
}
