import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function publicProfileQuery(services: FrontendServices, scope: string, identifier: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'public-profile', identifier], queryFn: ({ signal }) => services.account.publicProfile(identifier, signal) })
}
export function publicAuthorQuery(services: FrontendServices, scope: string, id: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'public-author', id], queryFn: ({ signal }) => services.account.publicProfile(id, signal), staleTime: 300000 })
}
