import { HydrationBoundary } from '@tanstack/react-query'
import { dehydrateRoute } from '@/lib/query/server'
import { makeQueryClient } from '@/lib/query/client'
import { loadServerAccount } from '@/lib/auth/account'
import { getServerScope, getServerServices } from '@/lib/api/services/server'
import { nodeQuery, progressQuery } from '@/features/library/queries'
import { flashcardQuery } from '@/features/study/flashcard-query'
import { FlashcardFocus } from '@/features/study/flashcard-focus.client'
import type { SearchValues } from '@/lib/query/url'

export default async function Page({ searchParams }: { searchParams: Promise<SearchValues> }) {
  const [account, services, scope, values] = await Promise.all([loadServerAccount(), getServerServices(), getServerScope(), searchParams])
  const id = typeof values.node === 'string' ? values.node : account?.library_node_id
  const client = makeQueryClient()
  if (id) {
    const node = await client.query(nodeQuery(services, scope, id))
    if (node.reference_available !== false) await Promise.all([client.prefetchQuery(progressQuery(services, scope, id)), client.infiniteQuery(flashcardQuery(services, scope, id))])
  }
  return <HydrationBoundary state={dehydrateRoute(client)}><FlashcardFocus /></HydrationBoundary>
}
