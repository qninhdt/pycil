'use client'

import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import { useAccount } from '@/features/account/account.client'
import { contentsQuery, meaningsQuery, nodeQuery } from '@/features/library/queries'
import type { ContentsOptions, MeaningOptions } from '@/features/library/model'

export function useLibraryNode(id: string) {
  const { services, scope } = useServices()
  return useQuery(nodeQuery(services, scope, id))
}
export function useLibraryContents(id: string, options: ContentsOptions) {
  const { services, scope } = useServices(), account = useAccount()
  return useQuery({ ...contentsQuery(services, scope, id, options), enabled: account.status !== 'loading' })
}
export function useLibraryMeanings(id: string, options: MeaningOptions) {
  const { services, scope } = useServices()
  return useQuery({ ...meaningsQuery(services, scope, id, options),
    placeholderData: (previous, query) => query?.queryKey[3] === id ? previous : undefined })
}
