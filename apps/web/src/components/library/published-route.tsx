'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/components/application/providers'
import { PublicProfilePage } from '@/components/account/public-profile-page'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { useServices } from '@/lib/services/provider'
import { publishedHref, type LibraryTab } from '@/lib/library-model'
import { LibraryPage } from './library-page'

export function PublishedRoute({ identifier, nodeId, tab }: { identifier: string; nodeId?: string; tab?: LibraryTab }) {
  const account = useAccount()
  const { services, scope } = useServices()
  const own = !!account.profile && (identifier === 'me' || identifier === account.profile.id || identifier === account.profile.handle)
  const owner = identifier === 'me' ? account.profile?.id : identifier
  const query = useQuery({ queryKey: [services.mode, scope, 'public-profile', owner], queryFn: ({ signal }) => services.account.publicProfile(owner!, signal), enabled: !!owner && !own })
  if (account.status === 'loading') return <HomeLoading label="your account" />
  if (own) return <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId ?? account.profile!.published_node_id} tab={tab} />
  if (!owner) return <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId} tab={tab} />
  if (query.isPending) return <HomeLoading label="Published library" />
  if (query.isError) return <HomeFailure label="Published library" error={query.error} retry={() => { void query.refetch() }} />
  if (query.data.id === account.profile?.id) return <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId ?? account.profile.published_node_id} tab={tab} />
  return <PublicProfilePage identifier={owner} nodeId={nodeId} publishedBase={publishedHref(query.data.id)} />
}
