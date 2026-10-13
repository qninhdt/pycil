import { dehydrateRoute } from '@/lib/query/server'
import 'server-only'
import { prefetchAuthors } from './authors.server'

import { HydrationBoundary } from '@tanstack/react-query'
import { ApiError } from '@/lib/api/error'
import { redirect } from 'next/navigation'
import { makeQueryClient } from '@/lib/query/client'
import { getServerScope, getServerServices } from '@/lib/api/services/server'
import { loadServerAccount } from '@/lib/auth/account'
import { isDeck, nodeHref } from '@/features/library/model'
import { contentsOptions, meaningOptions, contentsQuery, meaningsQuery, nodeQuery, progressQuery } from './queries'
import { searchParams, type SearchValues } from '@/lib/query/url'
import { LibraryPage, LibraryNodePage } from '@/features/library/library-page.client'

export async function LibraryRoute({ nodeId, space = 'personal', words = false, search = {} }: { nodeId?: string; space?: 'personal' | 'published'; words?: boolean; search?: SearchValues }) {
  const [account, services, scope] = await Promise.all([loadServerAccount(), getServerServices(), getServerScope()])
  const id = nodeId ?? (space === 'published' ? account?.published_node_id : account?.personal_node_id)
  const client = makeQueryClient()
  if (id) {
    const node = await client.query(nodeQuery(services, scope, id)).catch(error => {
      if (services.mode === 'mock' && error instanceof ApiError && error.status === 404) return null
      throw error
    })
    if (!node) return <LibraryPage nodeId={id} tab={words ? 'words' : 'overview'} routeSpace={space} />
    if (node.space !== space || space === 'personal' && node.owner_id !== account?.id) redirect(nodeHref(node, words ? 'words' : 'overview', account?.id))
    if (node.reference_available !== false) {
      const params = searchParams(search)
      const [, page] = await Promise.all([
        client.prefetchQuery(progressQuery(services, scope, id)),
        words ? client.query(meaningsQuery(services, scope, id, meaningOptions(params)))
          : isDeck(node) ? client.query(meaningsQuery(services, scope, id, { cursor: undefined, limit: 12 }))
            : client.query(contentsQuery(services, scope, node.target?.id ?? id, contentsOptions(params))),
      ])
      if ('nodes' in page) await prefetchAuthors(client, services, scope, page.nodes, account?.id)
    }
  }
  const create = search.create === 'deck' || search.create === 'folder' ? search.create : undefined
  return <HydrationBoundary state={dehydrateRoute(client)}>{nodeId ? <LibraryNodePage nodeId={nodeId} routeSpace={space} /> : <LibraryPage tab="overview" routeSpace={space} create={create} />}</HydrationBoundary>
}
