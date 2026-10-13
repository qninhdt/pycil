import { QueryClient, defaultShouldDehydrateQuery, isServer } from '@tanstack/react-query'

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        gcTime: 5 * 60 * 1000,
        retry: (attempt, error) =>
          attempt < 1 &&
          (!('status' in error) || ![401, 403, 404, 422].includes(Number((error as { status?: number }).status))),
        refetchOnWindowFocus: true,
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

let browserQueryClient: QueryClient | undefined = undefined

export function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient()
  } else {
    if (!browserQueryClient) browserQueryClient = makeQueryClient()
    return browserQueryClient
  }
}
