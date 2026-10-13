'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { useAccount } from '@/features/account/account.client'
import { Button } from '@/components/ui/button'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useServices } from '@/lib/api/services/provider.client'
import { useAssistantView } from '@/features/assistant/current-view.client'
import { HomeFailure } from '@/features/home/home-state.client'
import { publicCollectionHref } from '@/features/library/model'
import { LibraryDestinationDialog } from './library-destination-dialog.client'
import { LibraryStudy } from './library-study.client'
import { progressQuery } from './queries'

export function PublicCollectionActions({ nodeId, name, targetId, ownerId }: { nodeId: string; name: string; targetId?: string; ownerId: string }) {
  useAssistantView(nodeId)
  const t = useTranslations('library')
  const account = useAccount(), { services, scope } = useServices(), queryClient = useQueryClient()
  const [picking, setPicking] = useState(false)
  const progress = useQuery({ ...progressQuery(services, scope, nodeId), enabled: account.status === 'ready' })
  if (account.status !== 'ready' || !account.profile) return <Button asChild variant="outline" className="mt-4"><Link href={`/login?returnTo=${encodeURIComponent(publicCollectionHref(ownerId, nodeId))}`}>{t('signInToSaveOrStudy')}</Link></Button>
  return <div className="mt-4">
    <Button variant="outline" onClick={() => setPicking(true)}>{t('saveToPersonal')}</Button>
    {progress.isError ? <HomeFailure label={t('studyActions').toLowerCase()} error={progress.error} retry={() => { void progress.refetch() }} /> : progress.data && <LibraryStudy summary={progress.data} nodeId={nodeId} publishedOwner={ownerId} />}
    {picking && <LibraryDestinationDialog open profile={account.profile} kind="folder" spaceOnly="personal" action={t('saveReference')} onOpenChange={setPicking} onConfirm={async destination => {
      await services.library.createReference(destination.id, targetId ?? nodeId, name, new AbortController().signal)
      await invalidateLibrary(queryClient, services.mode, scope)
      toast.success(t('referenceSaved'))
    }} />}
  </div>
}
