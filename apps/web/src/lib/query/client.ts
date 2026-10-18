import { webConfig } from '@/config'
import { QueryClient, defaultShouldDehydrateQuery, isServer } from '@tanstack/react-query'

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: webConfig.query.staleMs,
        gcTime: webConfig.query.gcMs,
        retry: (attempt, error) =>
          attempt < webConfig.query.retries &&
          (!('status' in error) || ![401, 403, 404, 422].includes(Number((error as { status?: number }).status))),
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
      dehydrate: {
        shouldDehydrateQuery: query =>
          defaultShouldDehydrateQuery(query) || query.state.status === 'pending',
      },
    },
  })
}

let browserCache: { scope: string; client: QueryClient } | undefined

export function getQueryClient(scope: string): QueryClient {
  if (isServer) return makeQueryClient()
  if (browserCache?.scope !== scope) {
    if (browserCache) { void browserCache.client.cancelQueries(); browserCache.client.clear() }
    browserCache = { scope, client: makeQueryClient() }
  }
  return browserCache.client
}
