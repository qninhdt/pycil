import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function publicNodeQuery(services: FrontendServices, scope: string, id: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'public-node', id], queryFn: ({ signal }) => services.library.publicNode(id, signal) })
}
export function publicMeaningsQuery(services: FrontendServices, scope: string, id: string, cursor?: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'public-meanings', id, cursor], queryFn: ({ signal }) => services.library.publicMeanings(id, cursor, signal) })
}
export function publicContentsQuery(services: FrontendServices, scope: string, id: string, cursor?: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'public-contents', id, cursor], queryFn: ({ signal }) => services.library.publicContents(id, cursor, signal) })
}
