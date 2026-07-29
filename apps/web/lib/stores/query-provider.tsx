"use client"

import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

/**
 * One cache for the whole app, created once per mount and mounted only in the
 * root layout. A second instance would let the palette and the study screen
 * disagree about the same deck.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Study and library reads are cheap and staleness is confusing when
            // a learner just added a word, so refetch rather than serve stale.
            staleTime: 30_000,
            retry: 1,
            // Both refetch triggers are off. A refetch is only safe for a pure
            // read, and the one call that is not pure — advancing a session —
            // destroys a question when it runs twice. It is a server action with
            // no query key, so it cannot be reached from here; these stay off so
            // that remains true of anything added later by default.
            refetchOnWindowFocus: false,
            refetchOnReconnect: false,
          },
          mutations: {
            // Never retry a mutation on the caller's behalf. The API takes no
            // idempotency key, so a retry after a request that actually
            // succeeded applies the change twice.
            retry: false,
          },
        },
      }),
  )

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
