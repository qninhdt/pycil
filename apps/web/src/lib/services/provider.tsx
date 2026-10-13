'use client'

import { createContext, useContext, useState } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import type { FrontendServices } from './contracts'

const ServicesContext = createContext<{ services: FrontendServices; scope: string } | null>(null)

export function ServicesProvider({ services, scope, children }: { services: FrontendServices; scope: string; children: React.ReactNode }) {
  const [queryClient] = useState(() => getQueryClient())
  return <ServicesContext.Provider value={{ services, scope }}><QueryClientProvider client={queryClient}>{children}</QueryClientProvider></ServicesContext.Provider>
}

export function useServices() {
  const context = useContext(ServicesContext)
  if (!context) throw new Error('ServicesProvider is missing.')
  return context
}
