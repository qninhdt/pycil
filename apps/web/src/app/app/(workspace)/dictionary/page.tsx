import { dehydrate, HydrationBoundary } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import { getServerServices } from '@/lib/services/server'
import { loadServerAccount } from '@/lib/server-account'
import { DictionaryPage } from '@/components/dictionary/dictionary-page'
import type { WordSearch } from '@/lib/dictionary-model'

export const metadata = { title: 'Dictionary' }

export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams
  const query = typeof q === 'string' ? q.trim() : ''
  const queryClient = getQueryClient()
  const services = await getServerServices()
  const account = await loadServerAccount()
  const scope = account?.id ?? 'signed-out'

  if (query) {
    try {
      const searchResult = await queryClient.query<WordSearch>({
        queryKey: [services.mode, scope, 'dictionary-search', query],
        queryFn: ({ signal }) => services.dictionary.search(query, signal),
      }).catch(() => null)

      const topWordHit = searchResult?.items?.find(hit => hit.kind === 'word')
      if (topWordHit && topWordHit.word_id) {
        await Promise.all([
          queryClient.query({
            queryKey: [services.mode, scope, 'dictionary-word', topWordHit.word_id],
            queryFn: ({ signal }) => services.dictionary.word(topWordHit.word_id, signal),
          }).catch(() => null),
          ...(account?.id ? [
            queryClient.query({
              queryKey: [services.mode, scope, 'dictionary-context', topWordHit.word_id],
              queryFn: ({ signal }) => services.dictionary.context(topWordHit.word_id, signal),
            }).catch(() => null),
          ] : []),
        ])
      }
    } catch {
      // Graceful fallback: client will retry/fetch if server encounters a transient issue
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <DictionaryPage initialQuery={query} />
    </HydrationBoundary>
  )
}
