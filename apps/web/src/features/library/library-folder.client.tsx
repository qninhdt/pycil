'use client'

import { useDeferredValue, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { contentsOptions } from '@/features/library/queries'
import { updateUrl } from '@/lib/query/url'
import { useTranslations } from 'next-intl'
import { LayoutGrid, List, Plus } from '@/components/artwork/artwork'
import { Motif } from '@/components/artwork/artwork'
import { useAccount } from '@/features/account/account.client'
import { HomeFailure, HomeLoading, StatusShape } from '@/features/home/home-state.client'
import { useLibraryContents } from '@/features/library/use-library.client'
import { libraryHref, libraryMotif, libraryNodeKind, libraryNodeLabel, publishedHref } from '@/features/library/model'
import { Button } from '@/components/ui/button'
import { LibraryNodeIcon } from './library-node-icon'
import { LibraryNodeActions } from './library-node-actions.client'
import { LibraryNodeForm } from './library-node-form.client'
import { LibraryAuthor } from './library-author.client'
import type { LibraryNode } from '@/lib/api/study'
import { LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared.client'

const viewKey = 'pycil-library-view'
type ViewMode = 'cards' | 'list'

function NodeCounts({ node }: { node: LibraryNode }) {
  const t = useTranslations('library')
  return node.summary ? <div className="group-data-[view=list]:m-0 max-[767px]:group-data-[view=list]:col-start-2 max-[767px]:group-data-[view=list]:row-[1/4] flex flex-wrap items-center gap-4 text-[11px] leading-normal [&_>_span]:inline-flex [&_>_span]:items-center [&_>_span]:gap-1.5 [&_svg]:size-2.5"><span><StatusShape state="due" />{node.summary.due} {t('due')}</span><span><StatusShape state="new" />{node.summary.new} {t('new')}</span></div> : <span className="text-muted-foreground text-xs leading-normal mt-1">{t('notAvailable')}</span>
}

function NodeItem({ node, view, space, parentId, publishedBase }: { node: LibraryNode; view: ViewMode; space: 'personal' | 'published'; parentId: string; publishedBase?: string }) {
  const t = useTranslations('library')
  const folder = libraryNodeKind(node) === 'folder'
  const href = space === 'published'
    ? publishedBase ? `${publishedBase}/${encodeURIComponent(node.id)}` : publishedHref(node.id)
    : libraryHref(node.id)
  const detail = folder ? `${node.type === 'reference' ? t('folderReference') : ''}${node.summary ? `${t('deckCount', { count: node.summary.reachable_decks })} · ${t('wordsTotal', { count: node.summary.total })}` : t('summaryUnavailable')}`
    : `${libraryNodeLabel(node)}${node.summary ? ` · ${t('wordsTotal', { count: node.summary.total })}` : ''}`
  return <li className="library-node-item relative min-w-0 border border-border bg-background transition-colors hover:bg-accent focus-within:bg-accent group-data-[view=list]:border-0 group-data-[view=list]:border-b group-data-[view=list]:border-border" data-view={view}>
    <Link href={href} className="relative flex min-h-[164px] items-start gap-3 overflow-hidden py-[18px] pr-11 pb-[34px] pl-[18px] focus-visible:outline-2 focus-visible:-outline-offset-[3px] focus-visible:outline-ring [&>.bauhaus-icon]:size-7 [&>.bauhaus-icon]:shrink-0 group-data-[view=list]:min-h-[74px] group-data-[view=list]:items-center group-data-[view=list]:py-3 group-data-[view=list]:pr-[54px] group-data-[view=list]:pb-3 group-data-[view=list]:pl-[14px]" aria-label={t('openItemAria', { name: node.name, label: libraryNodeLabel(node) })}>
      <LibraryNodeIcon node={node} />
      <div className="relative z-[1] min-w-0 [&_h3]:text-[15px] [&_h3]:leading-[1.35] [&_h3]:wrap-anywhere [&_p]:my-[5px] [&_p]:mb-[7px] [&_p]:text-xs [&_p]:leading-[1.4] [&_p]:text-muted-foreground group-data-[view=list]:grid group-data-[view=list]:w-full group-data-[view=list]:grid-cols-[minmax(180px,1fr)_minmax(130px,.8fr)_minmax(120px,.7fr)_auto] group-data-[view=list]:items-center group-data-[view=list]:gap-4 group-data-[view=list]:[&_p]:m-0 max-[767px]:group-data-[view=list]:grid-cols-[minmax(0,1fr)_auto] max-[767px]:group-data-[view=list]:gap-x-[10px] max-[767px]:group-data-[view=list]:gap-y-[3px] max-[767px]:group-data-[view=list]:[&_p]:col-start-1"><h3>{node.name}</h3><p>{detail}</p><LibraryAuthor ownerId={node.owner_id} /><NodeCounts node={node} /></div>
      {view === 'cards' && <Motif name={libraryMotif(node.id)} data-motif={libraryMotif(node.id)} className="library-node-motif absolute right-0 bottom-0 w-[100px] h-[75px] opacity-85 pointer-events-none" />}
    </Link>
    <LibraryNodeActions node={node} space={space} parentId={parentId} />
  </li>
}

export function LibraryFolder({ nodeId, name, space, canCreate, publishedBase }: { nodeId: string; name: string; space: 'personal' | 'published'; canCreate: boolean; publishedBase?: string }) {
  const t = useTranslations('library')
  const account = useAccount()
  const params = useSearchParams()
  const search = params.get('q') ?? '', q = useDeferredValue(search.trim())
  const cursors = params.getAll('cursor')
  const setCursors = (values: string[]) => updateUrl({ cursor: values })
  const [view, setView] = useState<ViewMode>('cards')
  const [creating, setCreating] = useState<'deck' | 'folder' | null>(null)
  useEffect(() => { try { setView(localStorage.getItem(viewKey) === 'list' ? 'list' : 'cards') } catch { /* View remains usable without storage. */ } }, [])
  const changeView = (next: ViewMode) => { setView(next); try { localStorage.setItem(viewKey, next) } catch { /* Optional device preference. */ } }
  const query = useLibraryContents(nodeId, { ...contentsOptions(params), q })
  const nodes = query.data?.nodes ?? [], folders = nodes.filter(node => libraryNodeKind(node) === 'folder'), decks = nodes.filter(node => libraryNodeKind(node) !== 'folder')
  const searchChange = (value: string) => updateUrl({ q: value, cursor: null }, true)
  return <section className="[&_>_section_+_section]:mt-6" aria-label={t('folderContents')} aria-busy={query.isFetching || q !== search}>
    <div className="library-contents-toolbar flex justify-between items-center gap-4 mb-5 max-[767px]:items-stretch max-[767px]:flex-col"><LibrarySearch value={search} onChange={searchChange} label={t('searchFolder')} />
      <div className="flex items-center gap-2 flex-wrap max-[767px]:justify-between max-[767px]:gap-2">
        <div className="inline-flex gap-0.5 p-0.5 border border-border [&_[aria-pressed=true]]:bg-foreground [&_[aria-pressed=true]]:text-background" role="group" aria-label={t('viewMode')}><Button size="icon-sm" variant="ghost" className="rounded-none" aria-label={t('cardView')} aria-pressed={view === 'cards'} onClick={() => changeView('cards')}><LayoutGrid aria-hidden="true" /></Button><Button size="icon-sm" variant="ghost" className="rounded-none" aria-label={t('listView')} aria-pressed={view === 'list'} onClick={() => changeView('list')}><List aria-hidden="true" /></Button></div>
        {canCreate && <><Button variant="outline" size="sm" className="rounded-none max-[767px]:flex-1" onClick={() => setCreating('folder')}><Plus aria-hidden="true" />{t('newFolder')}</Button><Button size="sm" className="rounded-none max-[767px]:flex-1" onClick={() => setCreating('deck')}><Plus aria-hidden="true" />{t('newDeck')}</Button></>}
      </div>
    </div>
    {query.isError ? <HomeFailure label={t('folderContents').toLowerCase()} error={query.error} retry={() => { void query.refetch() }} /> : query.isPending ? <HomeLoading label={t('folderContents').toLowerCase()} />
      : nodes.length === 0 ? <LibraryEmpty title={q ? t('noMatchingContent') : t('folderEmpty')} description={q ? undefined : t('createDeckOrFolderPrompt')} reset={q ? () => searchChange('') : undefined} /> : <>
        {folders.length > 0 && <section aria-labelledby="library-subfolders-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-subfolders-title">{q ? t('matchingFolders') : t('subfolders')}</h2></div>
          <ul className="library-node-grid group grid grid-cols-3 gap-3 data-[view=list]:grid-cols-1 data-[view=list]:gap-0 data-[view=list]:border-t data-[view=list]:border-border max-[1199px]:grid-cols-2 max-[767px]:grid-cols-1" data-view={view}>{folders.map(node => <NodeItem key={node.id} node={node} view={view} space={space} parentId={nodeId} publishedBase={publishedBase} />)}</ul>
        </section>}
        {decks.length > 0 && <section aria-labelledby="library-decks-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-decks-title">{q ? t('matchingDecks') : t('decks')}</h2></div>
          <ul className="library-node-grid group grid grid-cols-3 gap-3 data-[view=list]:grid-cols-1 data-[view=list]:gap-0 data-[view=list]:border-t data-[view=list]:border-border max-[1199px]:grid-cols-2 max-[767px]:grid-cols-1" data-view={view}>{decks.map(node => <NodeItem key={node.id} node={node} view={view} space={space} parentId={nodeId} publishedBase={publishedBase} />)}</ul>
        </section>}
        {(query.data?.next_cursor || cursors.length > 0) && <LibraryPagination page={cursors.length + 1} busy={query.isFetching}
          previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={query.data?.next_cursor ? () => setCursors([...cursors, query.data!.next_cursor!]) : undefined} />}
      </>}
    {creating && account.profile && <LibraryNodeForm key={`${nodeId}:${creating}`} profile={account.profile} kind={creating} open onOpenChange={open => { if (!open) setCreating(null) }} parent={{ id: nodeId, name, space }} />}
  </section>
}
