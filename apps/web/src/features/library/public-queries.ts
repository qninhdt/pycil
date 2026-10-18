import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function publicNodeQuery(services: FrontendServices, id: string) {
  return queryOptions({ queryKey: [services.mode, 'public', 'public-node', id], queryFn: ({ signal }) => services.library.publicNode(id, signal) })
}
