import 'server-only'

import { HydrationBoundary } from '@tanstack/react-query'
import { cache } from 'react'
import { getPublicServices } from '@/lib/api/services/server'
import { makeQueryClient } from '@/lib/query/client'
import { dehydrateRoute } from '@/lib/query/server'
import { searchParams, type SearchValues } from '@/lib/query/url'
import { publicMetadata } from '@/lib/seo'
import { publicProfileQuery, publicAuthorQuery } from '@/features/account/public-queries'
import { PublicProfilePage } from '@/features/account/public-profile-page.client'
import { publicProfile, publicNode } from './public-server'
import { contentsOptions, contentsQuery, meaningOptions, meaningsQuery } from './queries'
import { isDeck, publicCollectionHref } from './model'
import { publicNodeQuery } from './public-queries'
import { PublicNodeView } from './public-node.client'

export type PublicPageProps = { params: Promise<{ identifier: string; nodeId?: string }>; searchParams: Promise<SearchValues> }

const initialPublicPage = cache(async (identifier: string, nodeId: string | undefined, words: boolean, query: string) => {
  const services = getPublicServices(), client = makeQueryClient()
  const profile = (await publicProfile(identifier))!
  const path = publicCollectionHref(profile.handle || profile.id, nodeId, words ? 'words' : 'overview')
  client.setQueryData(publicProfileQuery(services, identifier).queryKey, profile)
  client.setQueryData(publicAuthorQuery(services, profile.id).queryKey, profile)
  const params = new URLSearchParams(query)
  if (!nodeId) {
    const page = await client.fetchQuery(contentsQuery(services, 'public', profile.published_node_id, contentsOptions(params), true))
    return { client, profile, path, title: profile.display_name || profile.handle || 'Learner', description: profile.bio || 'Published vocabulary collections on Pycil.', nonempty: page.nodes.length > 0 }
  }
  const node = (await publicNode(identifier, nodeId))!
  client.setQueryData(publicNodeQuery(services, nodeId).queryKey, node)
  let nonempty = false
  if (node.reference_available !== false) {
    if (words || isDeck(node)) {
      const page = await client.fetchQuery(meaningsQuery(services, 'public', nodeId, words ? meaningOptions(params) : { limit: 12 }, true))
      nonempty = page.senses.length > 0
    } else {
      const page = await client.fetchQuery(contentsQuery(services, 'public', node.target?.id ?? nodeId, contentsOptions(params), true))
      nonempty = page.nodes.length > 0
    }
  }
  return { client, profile, path, title: node.name, description: node.description || `Vocabulary ${isDeck(node) ? 'deck' : 'folder'} by ${profile.display_name || profile.handle || 'a Pycil learner'}.`, nonempty }
})

async function pageData(props: PublicPageProps, words: boolean) {
  const { identifier, nodeId } = await props.params
  const params = searchParams(await props.searchParams)
  return { identifier, nodeId, params, data: await initialPublicPage(identifier, nodeId, words, params.toString()) }
}

export async function publicPageMetadata(props: PublicPageProps, words = false) {
  const { data, params } = await pageData(props, words)
  const variant = ['q', 'cursor', 'state', 'sort'].some(key => params.has(key))
  const canonical = params.has('cursor') ? `${data.path}?${params}` : data.path
  return publicMetadata({ title: data.title, description: data.description, path: canonical, image: `${data.path.replace(/\/words$/, '')}/opengraph-image`, index: !words && !variant && data.nonempty })
}

export async function PublicPage(props: PublicPageProps & { words?: boolean }) {
  const { identifier, nodeId, data } = await pageData(props, Boolean(props.words))
  return <HydrationBoundary state={dehydrateRoute(data.client)}>{nodeId
    ? <PublicNodeView key={nodeId} identifier={data.profile.handle || data.profile.id} nodeId={nodeId} />
    : <PublicProfilePage identifier={identifier} publishedBase={publicCollectionHref(data.profile.handle || data.profile.id)} />}</HydrationBoundary>
}
