import { prefetchAuthors } from '@/features/library/authors.server'
import { dehydrateRoute } from '@/lib/query/server'
import { HydrationBoundary } from '@tanstack/react-query'
import { makeQueryClient } from '@/lib/query/client'
import { getServerServices, getServerScope } from '@/lib/api/services/server'
import { discoveryState, discoveryQuery } from '@/features/library/discovery-queries'
import { searchParams, type SearchValues } from '@/lib/query/url'
import { DiscoveryPage } from '@/features/library/discovery-page.client'

export const metadata = { title: 'Discovery', description: 'Explore community decks, folders, and vocabulary collections published by learners on Pycil.' }
export default async function Page({ searchParams: values }: { searchParams: Promise<SearchValues> }) {
  const [services, scope] = await Promise.all([getServerServices(), getServerScope()])
  const client = makeQueryClient()
  const page = await client.query(discoveryQuery(services, scope, discoveryState(searchParams(await values))))
  await prefetchAuthors(client, services, scope, page.nodes)
  return <HydrationBoundary state={dehydrateRoute(client)}><DiscoveryPage /></HydrationBoundary>
}
