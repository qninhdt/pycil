'use client'

import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/services/provider'
import type { ContentsOptions, MeaningOptions } from '@/lib/library-model'

export function useLibraryNode(id: string) {
  const { services, scope } = useServices()
  return useQuery({ queryKey: [services.mode, scope, 'library-node', id], queryFn: ({ signal }) => services.library.details(id, signal) })
}

export function useLibraryContents(id: string, options: ContentsOptions) {
  const { services, scope } = useServices()
  return useQuery({ queryKey: [services.mode, scope, 'library-contents', id, options], queryFn: ({ signal }) => services.library.contents(id, options, signal) })
}

export function useLibraryMeanings(id: string, options: MeaningOptions) {
  const { services, scope } = useServices()
  return useQuery({ queryKey: [services.mode, scope, 'library-meanings', id, options], queryFn: ({ signal }) => services.library.meanings(id, options, signal) })
}
