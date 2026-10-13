import type { Metadata } from 'next'
import { dehydrate, HydrationBoundary } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import { getServerServices } from '@/lib/services/server'
import { loadServerAccount } from '@/lib/server-account'
import { DiscoveryPage } from '@/components/library/discovery-page'

export const metadata: Metadata = {
  title: 'Discovery — Explore Public Decks & Vocabulary',
  description: 'Explore community decks, folders, and vocabulary collections published by learners on Pycil.',
}

export default async function Page() {
  const queryClient = getQueryClient()
  const account = await loadServerAccount()
  const services = await getServerServices()
  const scope = account?.id ?? 'signed-out'

  try {
    await queryClient.query({
      queryKey: [services.mode, scope, 'discovery', '', 'all', undefined],
      queryFn: ({ signal }) => services.library.discovery({ limit: 12 }, signal),
    }).catch(() => null)
  } catch {
    // Graceful fallback to client fetching
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <DiscoveryPage />
    </HydrationBoundary>
  )
}
