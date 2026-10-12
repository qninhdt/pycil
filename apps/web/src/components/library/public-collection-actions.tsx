'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'
import { useAssistantView } from '@/hooks/use-assistant-view'
import { HomeFailure } from '@/components/home/home-state'
import { publishedHref } from '@/lib/library-model'
import { LibraryDestinationDialog } from './library-destination-dialog'
import { LibraryStudy } from './library-study'

export function PublicCollectionActions({ nodeId, name, targetId, ownerId }: { nodeId: string; name: string; targetId?: string; ownerId: string }) {
  useAssistantView(nodeId)
  const t = useTranslations('library')
  const account = useAccount(), { services, scope } = useServices(), queryClient = useQueryClient()
  const [picking, setPicking] = useState(false)
  const details = useQuery({ queryKey: [services.mode, scope, 'library-node', nodeId], queryFn: ({ signal }) => services.library.details(nodeId, signal), enabled: account.status === 'ready' })
  if (account.status !== 'ready' || !account.profile) return <Button asChild variant="outline" className="mt-4"><Link href={`/login?returnTo=${encodeURIComponent(publishedHref(ownerId, nodeId))}`}>{t('signInToSaveOrStudy')}</Link></Button>
  return <div className="mt-4">
    <Button variant="outline" onClick={() => setPicking(true)}>{t('saveToPersonal')}</Button>
    {details.isError ? <HomeFailure label={t('studyActions').toLowerCase()} error={details.error} retry={() => { void details.refetch() }} /> : details.data?.summary && <LibraryStudy summary={details.data.summary} nodeId={nodeId} publishedOwner={ownerId} />}
    {picking && <LibraryDestinationDialog open profile={account.profile} kind="FOLDER" spaceOnly="personal" action={t('saveReference')} onOpenChange={setPicking} onConfirm={async destination => {
      await services.library.createReference(destination.id, targetId ?? nodeId, name, new AbortController().signal)
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      toast.success(t('referenceSaved'))
    }} />}
  </div>
}
