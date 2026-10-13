import { dehydrateRoute } from '@/lib/query/server'
import { HydrationBoundary } from '@tanstack/react-query'
import { AppShell } from '@/components/shell/app-shell'
import { PublicNodeView } from '@/features/library/public-node.client'
import { publicNode } from '@/features/library/public-server'
import { publicNodeQuery, publicMeaningsQuery, publicContentsQuery } from '@/features/library/public-queries'
import { getServerServices, getServerScope } from '@/lib/api/services/server'
import { makeQueryClient } from '@/lib/query/client'
import { isDeck } from '@/features/library/model'
import { progressQuery } from '@/features/library/queries'
import { searchParams, type SearchValues } from '@/lib/query/url'

type Props = { params: Promise<{ identifier: string; nodeId: string }>; searchParams: Promise<SearchValues> }
export async function generateMetadata({ params }: Props) {
  const { identifier, nodeId } = await params
  const node = await publicNode(identifier, nodeId)
  return { title: node?.name ?? 'Published collection', description: node?.description || 'Published vocabulary on Pycil.' }
}
export default async function Page({ params, searchParams: values }: Props) {
  const { identifier, nodeId } = await params
  const [node, services, scope] = await Promise.all([publicNode(identifier, nodeId), getServerServices(), getServerScope()])
  const client = makeQueryClient(), cursor = searchParams(await values).getAll('cursor').at(-1)
  if (!node) return <AppShell><PublicNodeView identifier={identifier} nodeId={nodeId} /></AppShell>
  client.setQueryData(publicNodeQuery(services, scope, nodeId).queryKey, node)
  if (node.reference_available !== false) {
    await Promise.all([
      isDeck(node) ? client.query(publicMeaningsQuery(services, scope, nodeId, cursor)) : client.query(publicContentsQuery(services, scope, node.target?.id ?? nodeId, cursor)),
      scope !== 'signed-out' ? client.prefetchQuery(progressQuery(services, scope, nodeId)) : undefined,
    ])
  }
  return <HydrationBoundary state={dehydrateRoute(client)}><AppShell><PublicNodeView identifier={identifier} nodeId={nodeId} /></AppShell></HydrationBoundary>
}
