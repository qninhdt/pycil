import { webConfig } from '@/config'
import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function publicProfileQuery(services: FrontendServices, identifier: string) {
  return queryOptions({ queryKey: [services.mode, 'public', 'public-profile', identifier], queryFn: ({ signal }) => services.account.publicProfile(identifier, signal) })
}
export function publicAuthorQuery(services: FrontendServices, id: string) {
  return queryOptions({ queryKey: [services.mode, 'public', 'public-author', id], queryFn: ({ signal }) => services.account.publicProfile(id, signal), staleTime: webConfig.query.publicHeadingStaleMs })
}
