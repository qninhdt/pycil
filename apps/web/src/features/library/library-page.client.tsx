'use client'

import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import { progressQuery } from './queries'
import { useEffect } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import { HomeFailure } from '@/features/home/home-state.client'
import { LibraryPageSkeleton, LibrarySummarySkeleton } from './library-skeletons'
import { useAccount } from '@/features/account/account.client'
import { useLibraryNode } from '@/features/library/use-library.client'
import { useAssistantView } from '@/features/assistant/current-view.client'
import { isDeck, libraryHref, nodeHref, publishedHref } from '@/features/library/model'
import type { AccountProfile } from '@/lib/api/account'
import { LibraryHeader } from './library-header.client'
import { LibrarySummary } from './library-summary'
import { LibraryStudy } from './library-study.client'
import { useTranslations } from 'next-intl'
import { LibraryContent } from './library-content.client'
import { LibraryNodeForm } from './library-node-form.client'

export function LibraryView({ profile, nodeId, create, routeSpace }: { profile: AccountProfile; nodeId: string; create?: 'deck' | 'folder'; routeSpace: 'personal' | 'published' }) {
  const router = useRouter()
  const tab = usePathname()?.endsWith('/words') ? 'words' : 'overview'
  const query = useLibraryNode(nodeId)
  const { services, scope } = useServices()
  const progress = useQuery({ ...progressQuery(services, scope, nodeId), enabled: !!query.data && query.data.reference_available !== false })
  const summary = progress.data
  useAssistantView(nodeId)
  const t = useTranslations('library')
  const mismatch = !!query.data && (query.data.space !== routeSpace || (routeSpace === 'personal' && query.data.owner_id !== profile.id))
  useEffect(() => { if (mismatch && query.data) router.replace(nodeHref(query.data, undefined, profile.id)) }, [mismatch, query.data, router, profile.id])
  if (query.isPending) return <LibraryPageSkeleton space={routeSpace} tab={tab} />
  if (query.isError) return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeFailure label="Library material" error={query.error} retry={() => { void query.refetch() }} /><Button asChild variant="link"><Link href={libraryHref()}>{t('backToLibrary')}</Link></Button></div>
  if (mismatch) return <LibraryPageSkeleton space={routeSpace} tab={tab} />
  const node = query.data, deck = isDeck(node)
  const editable = node.owner_id === profile.id && node.role === 'normal'
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight" data-kind={deck ? 'deck' : 'folder'} data-system={node.role !== 'normal'}>
    <LibraryHeader node={node} profile={profile} editable={editable} />
    {node.reference_available === false ? <Empty className="min-h-60"><EmptyHeader><EmptyTitle>{t('referenceUnavailable')}</EmptyTitle><EmptyDescription>{t('referenceSourceGone')}</EmptyDescription></EmptyHeader><EmptyContent><Button asChild variant="outline"><Link href={nodeHref({ ...node, id: node.breadcrumbs.findLast(parent => parent.id !== node.id)?.id ?? (node.space === 'published' ? profile.published_node_id : profile.personal_node_id) })}>{t('backToFolder')}</Link></Button></EmptyContent></Empty>
      : <>
        {progress.isError ? <HomeFailure label="learning progress" error={progress.error} retry={() => { void progress.refetch() }} /> : progress.isPending ? <LibrarySummarySkeleton /> : <LibrarySummary summary={progress.data} />}
        {summary && <LibraryStudy key={node.id} nodeId={node.id} summary={summary} publishedOwner={node.space === 'published' ? node.owner_id : undefined} />}
        <LibraryContent node={node} profile={profile} summary={summary} editable={editable} />
      </>}
    {create && <LibraryNodeForm key={create} profile={profile} kind={create} open onOpenChange={open => { if (!open) router.replace(nodeHref(node, undefined, profile.id), { scroll: false }) }} destinationEnabled />}
  </div>
}

export function LibraryPage({ nodeId, create, routeSpace = 'personal' }: { nodeId?: string; create?: 'deck' | 'folder'; routeSpace?: 'personal' | 'published' }) {
  const account = useAccount()
  const tab = usePathname()?.endsWith('/words') ? 'words' : 'overview'
  const tNav = useTranslations('nav')
  if (account.status === 'ready' && account.profile) return <LibraryView key={`${account.profile.id}:${nodeId ?? routeSpace}`} profile={account.profile} nodeId={nodeId ?? (routeSpace === 'published' ? account.profile.published_node_id : account.profile.personal_node_id)} create={create} routeSpace={routeSpace} />
  if (account.status === 'loading') return <LibraryPageSkeleton space={routeSpace} tab={tab} />
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight">{account.status === 'error' ? <HomeFailure label={tNav('yourAccount')} error={new Error(account.error || 'Please retry.')} retry={account.retry} />
    : <Empty><EmptyHeader><EmptyTitle>{account.status === 'task' ? tNav('verificationNotice') : tNav('signInToLearn')}</EmptyTitle></EmptyHeader><EmptyContent><Button asChild><Link href={`/login?returnTo=${encodeURIComponent(routeSpace === 'published' ? publishedHref(nodeId, tab) : libraryHref(nodeId, tab))}`}>{account.status === 'task' ? tNav('continueVerification') : tNav('signIn')}</Link></Button></EmptyContent></Empty>}</div>
}
