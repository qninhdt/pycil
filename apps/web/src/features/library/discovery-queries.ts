import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

type DiscoveryState = { q: string; type: 'all' | 'folder' | 'deck'; cursor?: string }
export function discoveryState(params: Pick<URLSearchParams, 'get' | 'getAll'>): DiscoveryState {
  const type = params.get('type')
  return { q: params.get('q')?.trim() ?? '', type: type === 'folder' || type === 'deck' ? type : 'all', cursor: params.getAll('cursor').at(-1) }
}
export function discoveryQuery(services: FrontendServices, scope: string, { q, type, cursor }: DiscoveryState) {
  return queryOptions({ queryKey: [services.mode, scope, 'discovery', q, type, cursor],
    queryFn: ({ signal }) => services.library.discovery({ q, type: type === 'all' ? undefined : type, cursor, limit: 12 }, signal) })
}
