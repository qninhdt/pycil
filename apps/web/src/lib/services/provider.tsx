'use client'

import { createContext, useContext, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { FrontendServices } from './contracts'

const ServicesContext = createContext<{ services: FrontendServices; scope: string } | null>(null)

export function ServicesProvider({ services, scope, children }: { services: FrontendServices; scope: string; children: React.ReactNode }) {
  // This provider is keyed by authenticated session at the composition root.
  // SSR never shares a query client between requests; a new session gets a fresh cache.
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: {
    queries: { staleTime: 60000, gcTime: 300000, retry: (attempt, error) => attempt < 1 && (!('status' in error) || ![401, 403, 404, 422].includes(Number(error.status))), refetchOnWindowFocus: true },
    mutations: { retry: false },
  } }))
  return <ServicesContext.Provider value={{ services, scope }}><QueryClientProvider client={queryClient}>{children}</QueryClientProvider></ServicesContext.Provider>
}

export function useServices() {
  const context = useContext(ServicesContext)
  if (!context) throw new Error('ServicesProvider is missing.')
  return context
}
