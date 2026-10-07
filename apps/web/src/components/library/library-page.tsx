'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { useRouter, useSelectedLayoutSegment } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { useAccount } from '@/components/application/providers'
import { useLibraryNode } from '@/hooks/use-library'
import { dateLabel, isDeck, libraryHref, nodeHref, publishedHref, type LibraryTab } from '@/lib/library-model'
import type { AccountProfile } from '@/lib/api'
import { LibraryHeader } from './library-header'
import { LibrarySummary } from './library-summary'
import { LibraryStudy } from './library-study'
import { LibraryWords } from './library-words'
import { LibraryFolder } from './library-folder'
import { LibraryFlashcardPreview } from './library-flashcard-preview'
import { LibraryNodeForm } from './library-node-form'

export function LibraryView({ profile, nodeId, requestedTab, create, routeSpace }: { profile: AccountProfile; nodeId: string; requestedTab?: LibraryTab; create?: 'DECK' | 'FOLDER'; routeSpace: 'PERSONAL' | 'PUBLISHED' }) {
  const router = useRouter()
  const query = useLibraryNode(nodeId)
  const mismatch = !!query.data && (query.data.space !== routeSpace || query.data.owner_id !== profile.id)
  useEffect(() => { if (mismatch && query.data) router.replace(nodeHref(query.data)) }, [mismatch, query.data, router])
  if (query.isPending) return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeLoading label="Library material" /></div>
  if (query.isError) return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeFailure label="Library material" error={query.error} retry={() => { void query.refetch() }} /><Button asChild variant="link"><Link href={libraryHref()}>Back to My Library</Link></Button></div>
  if (mismatch) return <HomeLoading label="Library material" />
  const node = query.data, deck = isDeck(node)
  const editable = node.owner_id === profile.id && node.role === 'NORMAL'
  const tab = requestedTab ?? 'overview'
  const timezone = profile.settings?.timezone ?? 'UTC'
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight" data-kind={deck ? 'deck' : 'folder'} data-system={node.role !== 'NORMAL'}>
    <LibraryHeader node={node} profile={profile} editable={editable} />
    {node.reference_available === false ? <Empty className="min-h-60"><EmptyHeader><EmptyTitle>Reference unavailable.</EmptyTitle><EmptyDescription>The source is no longer available.</EmptyDescription></EmptyHeader><EmptyContent><Button asChild variant="outline"><Link href={nodeHref({ ...node, id: node.breadcrumbs.at(-1)?.id ?? node.id })}>Back to folder</Link></Button></EmptyContent></Empty>
      : node.summary && <>
        <LibrarySummary summary={node.summary} />
        <LibraryStudy key={node.id} nodeId={node.id} summary={node.summary} publishedOwner={node.space === 'PUBLISHED' ? node.owner_id : undefined} />
        <Tabs value={tab} onValueChange={value => router.push(nodeHref(node, value as LibraryTab), { scroll: false })}>
          <TabsList className="mb-3" aria-label="Library view"><TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="words">Words</TabsTrigger></TabsList>
          <TabsContent value="overview">{deck ? <div className="grid grid-cols-[minmax(0,2.4fr)_minmax(224px,1fr)] gap-6 border-t border-border pt-5 max-[959px]:grid-cols-1"><LibraryFlashcardPreview key={node.id} nodeId={node.id} total={node.summary.total} /><section className="border-l border-border pl-6 [&_dl]:grid [&_dl]:grid-cols-1 [&_dl_>_div]:flex [&_dl_>_div]:justify-between [&_dl_>_div]:gap-4 [&_dl_>_div]:py-3 [&_dl_>_div]:border-b [&_dl_>_div]:border-border [&_dl_>_div]:text-xs [&_dt]:text-muted-foreground [&_dd]:text-right max-[959px]:border-l-0 max-[959px]:border-t max-[959px]:border-border max-[959px]:pl-0 max-[959px]:pt-5 max-[767px]:[&_dl]:grid-cols-1 max-[767px]:[&_dl]:gap-0" aria-labelledby="library-about-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-about-title">Deck details</h2></div>
              <dl><div><dt>Created</dt><dd>{dateLabel(node.created_at, timezone)}</dd></div><div><dt>Updated</dt><dd>{dateLabel(node.updated_at, timezone)}</dd></div><div><dt>Last studied</dt><dd>{dateLabel(node.summary.last_studied_at, timezone)}</dd></div></dl>
            </section></div> : <LibraryFolder nodeId={node.target?.id ?? node.id} name={node.name} space={node.space === 'PUBLISHED' ? 'PUBLISHED' : 'PERSONAL'} canCreate={node.owner_id === profile.id && node.type === 'FOLDER' && node.space !== 'LIBRARY'} />}</TabsContent>
          <TabsContent value="words"><LibraryWords nodeId={node.id} summary={node.summary} folder={!deck} editable={editable && node.type !== 'REFERENCE'} timezone={timezone} /></TabsContent>
        </Tabs>
      </>}
    {create && <LibraryNodeForm key={create} profile={profile} kind={create} open onOpenChange={open => { if (!open) router.replace(nodeHref(node), { scroll: false }) }} destinationEnabled />}
  </div>
}

export function LibraryPage({ nodeId, tab, create, routeSpace = 'PERSONAL' }: { nodeId?: string; tab?: LibraryTab; create?: 'DECK' | 'FOLDER'; routeSpace?: 'PERSONAL' | 'PUBLISHED' }) {
  const account = useAccount()
  if (account.status === 'ready' && account.profile) return <LibraryView key={`${account.profile.id}:${nodeId ?? routeSpace}`} profile={account.profile} nodeId={nodeId ?? (routeSpace === 'PUBLISHED' ? account.profile.published_node_id : account.profile.personal_node_id)} requestedTab={tab} create={create} routeSpace={routeSpace} />
  return <div className="library-page w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight">{account.status === 'loading' ? <HomeLoading label="your account" /> : account.status === 'error' ? <HomeFailure label="your account" error={new Error(account.error || 'Please retry.')} retry={account.retry} />
    : <Empty><EmptyHeader><EmptyTitle>{account.status === 'task' ? 'Finish setting up your account.' : 'Sign in to open your Library.'}</EmptyTitle></EmptyHeader><EmptyContent><Button asChild><Link href={`/login?returnTo=${encodeURIComponent(routeSpace === 'PUBLISHED' ? publishedHref('me', nodeId, tab) : libraryHref(nodeId, tab))}`}>{account.status === 'task' ? 'Continue account setup' : 'Sign in'}</Link></Button></EmptyContent></Empty>}</div>
}

// Rendered by the persistent node layout so tab navigation retains keyboard focus.
export function LibraryNodePage({ nodeId, routeSpace = 'PERSONAL' }: { nodeId: string; routeSpace?: 'PERSONAL' | 'PUBLISHED' }) {
  const segment = useSelectedLayoutSegment()
  return <LibraryPage nodeId={nodeId} tab={segment === 'words' ? 'words' : 'overview'} routeSpace={routeSpace} />
}
