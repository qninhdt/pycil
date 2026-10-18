'use client'

import { useAccount } from '@/features/account/account.client'
import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import { contentsQuery, meaningsQuery, nodeQuery } from '@/features/library/queries'
import type { ContentsOptions, MeaningOptions } from '@/features/library/model'

export function useLibraryNode(id: string) {
  const { services, scope } = useServices()
  return useQuery(nodeQuery(services, scope, id))
}
export function useLibraryContents(id: string, options: ContentsOptions, publicRead?: boolean) {
  const { services, scope } = useServices()
  const account = useAccount()
  return useQuery({ ...contentsQuery(services, scope, id, options, publicRead), enabled: Boolean(publicRead) || account.status !== 'loading' })
}
export function useLibraryMeanings(id: string, options: MeaningOptions, publicRead?: boolean) {
  const { services, scope } = useServices()
  const account = useAccount()
  return useQuery({ enabled: Boolean(publicRead) || account.status !== 'loading', ...meaningsQuery(services, scope, id, options, publicRead),
    placeholderData: (previous, query) => query?.queryKey[3] === id ? previous : undefined })
}
