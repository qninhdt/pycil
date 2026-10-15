import { webConfig } from '@/config'
import { infiniteQueryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function flashcardQuery(services: FrontendServices, scope: string, nodeId: string) {
  return infiniteQueryOptions({ queryKey: [services.mode, scope, 'flashcards', nodeId], initialPageParam: undefined as string | undefined,
    queryFn: ({ signal, pageParam }) => services.library.meanings(nodeId, { cursor: pageParam, limit: webConfig.pagination.flashcards, state: 'all', sort: 'lemma_asc' }, signal),
    getNextPageParam: page => page.next_cursor ?? undefined, enabled: Boolean(nodeId) })
}
