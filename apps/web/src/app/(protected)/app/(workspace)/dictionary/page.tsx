import { dehydrateRoute } from '@/lib/query/server'
import { HydrationBoundary } from '@tanstack/react-query'
import { makeQueryClient } from '@/lib/query/client'
import { getServerServices, getServerScope } from '@/lib/api/services/server'
import { dictionaryQueries, dictionaryState } from '@/features/vocabulary/queries'
import { searchParams, type SearchValues } from '@/lib/query/url'
import { DictionaryPage } from '@/features/vocabulary/dictionary-page.client'

export const metadata = { title: 'Dictionary' }
export default async function Page({ searchParams: values }: { searchParams: Promise<SearchValues> }) {
  const state = dictionaryState(searchParams(await values))
  const [services, scope] = await Promise.all([getServerServices(), getServerScope()])
  const client = makeQueryClient(), queries = dictionaryQueries(services, scope, state.query, state.wordId)
  await Promise.all([
    ...(state.query ? [client.query(queries.search)] : []),
    ...(state.wordId !== null ? [client.query(queries.word), client.query(queries.context)] : []),
  ])
  return <HydrationBoundary state={dehydrateRoute(client)}><DictionaryPage /></HydrationBoundary>
}
