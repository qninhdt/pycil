import 'server-only'

import type { QueryClient } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'
import { publicAuthorQuery } from '@/features/account/public-queries'

export async function prefetchAuthors(client: QueryClient, services: FrontendServices, scope: string, nodes: { owner_id?: string }[], ownId?: string) {
  const owners = new Set(nodes.map(node => node.owner_id).filter(id => id && id !== ownId))
  await Promise.all([...owners].map(id => client.prefetchQuery(publicAuthorQuery(services, scope, id!))))
}
