'use client'

import { useEffect, useRef, useState } from 'react'
import { usePathname, useSearchParams, useRouter } from 'next/navigation'
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
import { LibraryDestinationDialog } from './library-destination-dialog.client'
import { LibraryStudy } from './library-study.client'
import { progressQuery } from './queries'
import { LibrarySummary } from './library-summary'

export function PublicCollectionActions({ nodeId, name, targetId, ownerId }: { nodeId: string; name: string; targetId?: string; ownerId: string }) {
  useAssistantView(nodeId)
  const t = useTranslations('library')
  const account = useAccount(), { services, scope } = useServices(), queryClient = useQueryClient()
  const [picking, setPicking] = useState(false)
  const path = usePathname(), params = useSearchParams(), router = useRouter()
  const action = params.get('action')
  const resumed = useRef(false)
  const progress = useQuery({ ...progressQuery(services, scope, nodeId), enabled: account.status === 'ready' })
  useEffect(() => {
    if (account.status !== 'ready' || resumed.current || (action !== 'save' && action !== 'study')) return
    resumed.current = true
    const url = new URL(window.location.href)
    url.searchParams.delete('action')
    window.history.replaceState(null, '', `${url.pathname}${url.search}`)
    if (action === 'save') setPicking(true)
    else router.push(`/app/learn?node=${encodeURIComponent(nodeId)}&selection=auto&owner=${encodeURIComponent(ownerId)}`)
  }, [account.status, action, nodeId, ownerId, router])
  const login = (intent: 'save' | 'study') => {
    const values = new URLSearchParams(params)
    values.set('action', intent)
    return `/login?returnTo=${encodeURIComponent(`${path}?${values}`)}`
  }
  if (account.status !== 'ready' || !account.profile) return <div className="flex flex-wrap gap-2 py-4">
    <Button asChild variant="outline"><Link href={login('save')}>{t('saveToPersonal')}</Link></Button>
    <Button asChild><Link href={login('study')}>{t('practice')}</Link></Button>
  </div>
  return <div className="mt-4">
    <Button variant="outline" onClick={() => setPicking(true)}>{t('saveToPersonal')}</Button>
    {progress.isError ? <HomeFailure label={t('studyActions').toLowerCase()} error={progress.error} retry={() => { void progress.refetch() }} /> : progress.data && <><LibrarySummary summary={progress.data} /><LibraryStudy summary={progress.data} nodeId={nodeId} publishedOwner={ownerId} /></>}
    {picking && <LibraryDestinationDialog open profile={account.profile} kind="folder" spaceOnly="personal" action={t('saveReference')} onOpenChange={setPicking} onConfirm={async destination => {
      await services.library.createReference(destination.id, targetId ?? nodeId, name, new AbortController().signal)
      await invalidateLibrary(queryClient, services.mode, scope)
      toast.success(t('referenceSaved'))
    }} />}
  </div>
}
