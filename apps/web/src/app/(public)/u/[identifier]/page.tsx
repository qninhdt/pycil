import { prefetchAuthors } from '@/features/library/authors.server'
import { dehydrateRoute } from '@/lib/query/server'
import { HydrationBoundary } from '@tanstack/react-query'
import { AppShell } from '@/components/shell/app-shell'
import { PublicProfilePage } from '@/features/account/public-profile-page.client'
import { publicProfile } from '@/features/library/public-server'
import { publicProfileQuery } from '@/features/account/public-queries'
import { contentsOptions, contentsQuery } from '@/features/library/queries'
import { getServerServices, getServerScope } from '@/lib/api/services/server'
import { makeQueryClient } from '@/lib/query/client'

import { searchParams, type SearchValues } from '@/lib/query/url'

type Props = { params: Promise<{ identifier: string }>; searchParams: Promise<SearchValues> }
export async function generateMetadata({ params }: Props) {
  const profile = await publicProfile((await params).identifier)
  return { title: `${profile?.display_name || profile?.handle || 'Learner'} — Profile`, description: profile?.bio || 'Published vocabulary collections on Pycil.' }
}
export default async function Page({ params, searchParams: values }: Props) {
  const { identifier } = await params
  const [profile, services, scope] = await Promise.all([publicProfile(identifier), getServerServices(), getServerScope()])
  const client = makeQueryClient()
  if (!profile) return <AppShell><PublicProfilePage identifier={identifier} publishedBase={`/u/${encodeURIComponent(identifier)}`} /></AppShell>
  client.setQueryData(publicProfileQuery(services, scope, identifier).queryKey, profile)
  const page = await client.query(contentsQuery(services, scope, profile.published_node_id, contentsOptions(searchParams(await values))))
  await prefetchAuthors(client, services, scope, page.nodes)
  return <HydrationBoundary state={dehydrateRoute(client)}><AppShell><PublicProfilePage identifier={identifier} publishedBase={`/u/${encodeURIComponent(identifier)}`} /></AppShell></HydrationBoundary>
}
