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
            refetchOnWindowFocus: false,
          },
        },
      }),
  )

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
