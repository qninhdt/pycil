'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/features/account/account.client'
import { HomeFailure } from '@/features/home/home-state.client'
import { LibraryPageSkeleton } from './library-skeletons'
import { useServices } from '@/lib/api/services/provider.client'
import { publicNodeQuery } from './public-queries'
import { PublicCollectionActions } from './public-collection-actions.client'
import { LibraryHeader } from './library-header.client'
import { LibraryContent } from './library-content.client'
import { LibraryEmpty } from './library-shared.client'
import { useTranslations } from 'next-intl'

export function PublicNodeView({ identifier, nodeId }: { identifier: string; nodeId: string }) {
  const { services } = useServices(), account = useAccount()
  const t = useTranslations('library')
  const query = useQuery(publicNodeQuery(services, nodeId))
  if (query.isPending) return <LibraryPageSkeleton space="published" publicRead />
  if (query.isError) return <HomeFailure label="Published material" error={query.error} retry={() => { void query.refetch() }} />
  const node = query.data
  const editable = account.status === 'ready' && node.owner_id === account.profile?.id && node.role === 'normal'
  return <div className="library-page w-full" data-kind={node.type}>
    <LibraryHeader node={node} profile={account.profile} editable={editable} publicIdentifier={identifier} />
    {node.reference_available === false ? <LibraryEmpty title={t('referenceUnavailable')} /> : <>
      <PublicCollectionActions nodeId={nodeId} name={node.name} ownerId={node.owner_id} targetId={node.target?.id} />
      <LibraryContent node={node} profile={account.profile} editable={editable} publicIdentifier={identifier} />
    </>}
  </div>
}
