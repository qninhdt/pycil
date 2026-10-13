'use client'

import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import { progressQuery } from './queries'
import { useEffect } from 'react'
import Link from 'next/link'
import { useRouter, usePathname } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import { HomeFailure, HomeLoading } from '@/features/home/home-state.client'
import { useAccount } from '@/features/account/account.client'
import { useLibraryNode } from '@/features/library/use-library.client'
import { useAssistantView } from '@/features/assistant/current-view.client'
import { dateLabel, isDeck, libraryHref, nodeHref, publishedHref, type LibraryTab } from '@/features/library/model'
import type { AccountProfile } from '@/lib/api/account'
import { LibraryHeader } from './library-header.client'
import { LibrarySummary } from './library-summary'
import { LibraryStudy } from './library-study.client'
import { LibraryWords } from './library-words.client'
import { LibraryFolder } from './library-folder.client'
import { LibraryFlashcardPreview } from './library-flashcard-preview.client'
import { useTranslations } from 'next-intl'
import { LibraryNodeForm } from './library-node-form.client'

export function LibraryView({ profile, nodeId, requestedTab, create, routeSpace }: { profile: AccountProfile; nodeId: string; requestedTab?: LibraryTab; create?: 'deck' | 'folder'; routeSpace: 'personal' | 'published' }) {
  const router = useRouter()
  const query = useLibraryNode(nodeId)
  const { services, scope } = useServices()
  const progress = useQuery({ ...progressQuery(services, scope, nodeId), enabled: !!query.data && query.data.reference_available !== false })
  const summary = progress.data
  useAssistantView(nodeId)
  const t = useTranslations('library')
  const mismatch = !!query.data && (query.data.space !== routeSpace || (routeSpace === 'personal' && query.data.owner_id !== profile.id))
  useEffect(() => { if (mismatch && query.data) router.replace(nodeHref(query.data, undefined, profile.id)) }, [mismatch, query.data, router, profile.id])
  if (query.isPending) return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeLoading label="Library material" /></div>
  if (query.isError) return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeFailure label="Library material" error={query.error} retry={() => { void query.refetch() }} /><Button asChild variant="link"><Link href={libraryHref()}>{t('backToLibrary')}</Link></Button></div>
  if (mismatch) return <HomeLoading label="Library material" />
  const node = query.data, deck = isDeck(node)
  const editable = node.owner_id === profile.id && node.role === 'normal'
  const tab = requestedTab ?? 'overview'
  const timezone = profile.settings?.timezone ?? 'UTC'
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight" data-kind={deck ? 'deck' : 'folder'} data-system={node.role !== 'normal'}>
    <LibraryHeader node={node} profile={profile} editable={editable} />
    {node.reference_available === false ? <Empty className="min-h-60"><EmptyHeader><EmptyTitle>{t('referenceUnavailable')}</EmptyTitle><EmptyDescription>{t('referenceSourceGone')}</EmptyDescription></EmptyHeader><EmptyContent><Button asChild variant="outline"><Link href={nodeHref({ ...node, id: node.breadcrumbs.findLast(parent => parent.id !== node.id)?.id ?? (node.space === 'published' ? profile.published_node_id : profile.personal_node_id) })}>{t('backToFolder')}</Link></Button></EmptyContent></Empty>
      : <>
        {progress.isError ? <HomeFailure label="learning progress" error={progress.error} retry={() => { void progress.refetch() }} /> : progress.isPending ? <HomeLoading label="learning progress" /> : <LibrarySummary summary={progress.data} />}
        {summary && <LibraryStudy key={node.id} nodeId={node.id} summary={summary} publishedOwner={node.space === 'published' ? node.owner_id : undefined} />}
        <Tabs value={tab} onValueChange={value => { const href = nodeHref(node, value as LibraryTab, profile.id); if (window.location.pathname !== href) window.history.pushState(null, '', href) }}>
          <TabsList className="mb-3" aria-label="Library view"><TabsTrigger value="overview">{t('overview')}</TabsTrigger><TabsTrigger value="words">{t('words')}</TabsTrigger></TabsList>
          <TabsContent value="overview">{deck ? <div className="grid grid-cols-[minmax(0,2.4fr)_minmax(224px,1fr)] gap-6 border-t border-border pt-5 max-[959px]:grid-cols-1"><LibraryFlashcardPreview key={node.id} nodeId={node.id} total={summary?.total} /><section className="border-l border-border pl-6 [&_dl]:grid [&_dl]:grid-cols-1 [&_dl_>_div]:flex [&_dl_>_div]:justify-between [&_dl_>_div]:gap-4 [&_dl_>_div]:py-3 [&_dl_>_div]:border-b [&_dl_>_div]:border-border [&_dl_>_div]:text-xs [&_dt]:text-muted-foreground [&_dd]:text-right max-[959px]:border-l-0 max-[959px]:border-t max-[959px]:border-border max-[959px]:pl-0 max-[959px]:pt-5 max-[767px]:[&_dl]:grid-cols-1 max-[767px]:[&_dl]:gap-0" aria-labelledby="library-about-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-about-title">{t('deckDetails')}</h2></div>
              <dl><div><dt>{t('created')}</dt><dd>{dateLabel(node.created_at, timezone)}</dd></div><div><dt>{t('updated')}</dt><dd>{dateLabel(node.updated_at, timezone)}</dd></div><div><dt>{t('lastStudied')}</dt><dd>{summary ? dateLabel(summary.last_studied_at, timezone) : '—'}</dd></div></dl>
            </section></div> : <LibraryFolder nodeId={node.target?.id ?? node.id} name={node.name} space={node.space === 'published' ? 'published' : 'personal'} canCreate={node.owner_id === profile.id && node.type === 'folder' && node.space !== 'library'} />}</TabsContent>
          <TabsContent value="words"><LibraryWords nodeId={node.id} summary={summary} folder={!deck} editable={editable && node.type !== 'reference'} timezone={timezone} /></TabsContent>
        </Tabs>
      </>}
    {create && <LibraryNodeForm key={create} profile={profile} kind={create} open onOpenChange={open => { if (!open) router.replace(nodeHref(node, undefined, profile.id), { scroll: false }) }} destinationEnabled />}
  </div>
}

export function LibraryPage({ nodeId, tab, create, routeSpace = 'personal' }: { nodeId?: string; tab?: LibraryTab; create?: 'deck' | 'folder'; routeSpace?: 'personal' | 'published' }) {
  const account = useAccount()
  const tNav = useTranslations('nav')
  if (account.status === 'ready' && account.profile) return <LibraryView key={`${account.profile.id}:${nodeId ?? routeSpace}`} profile={account.profile} nodeId={nodeId ?? (routeSpace === 'published' ? account.profile.published_node_id : account.profile.personal_node_id)} requestedTab={tab} create={create} routeSpace={routeSpace} />
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight">{account.status === 'loading' ? <HomeLoading label={tNav('yourAccount')} /> : account.status === 'error' ? <HomeFailure label={tNav('yourAccount')} error={new Error(account.error || 'Please retry.')} retry={account.retry} />
    : <Empty><EmptyHeader><EmptyTitle>{account.status === 'task' ? tNav('verificationNotice') : tNav('signInToLearn')}</EmptyTitle></EmptyHeader><EmptyContent><Button asChild><Link href={`/login?returnTo=${encodeURIComponent(routeSpace === 'published' ? publishedHref(nodeId, tab) : libraryHref(nodeId, tab))}`}>{account.status === 'task' ? tNav('continueVerification') : tNav('signIn')}</Link></Button></EmptyContent></Empty>}</div>
}

// Native history keeps the tab surface mounted while its query owner changes.
export function LibraryNodePage({ nodeId, routeSpace = 'personal' }: { nodeId: string; routeSpace?: 'personal' | 'published' }) {
  const pathname = usePathname()
  return <LibraryPage nodeId={nodeId} tab={pathname?.endsWith('/words') ? 'words' : 'overview'} routeSpace={routeSpace} />
}
