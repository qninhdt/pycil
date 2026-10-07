'use client'

import { useDeferredValue, useEffect, useState } from 'react'
import Link from 'next/link'
import { LayoutGrid, List, Plus } from '@/components/artwork/artwork'
import { Motif } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { HomeFailure, HomeLoading, StatusShape } from '@/components/home/home-state'
import { useLibraryContents } from '@/hooks/use-library'
import { libraryHref, libraryMotif, libraryNodeKind, libraryNodeLabel, publishedHref } from '@/lib/library-model'
import { Button } from '@/components/ui/button'
import { LibraryNodeIcon } from './library-node-icon'
import { LibraryNodeActions } from './library-node-actions'
import { LibraryNodeForm } from './library-node-form'
import { LibraryAuthor } from './library-author'
import type { LibraryNode } from '@/lib/home-api'
import { LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared'

const viewKey = 'pycil-library-view'
type ViewMode = 'cards' | 'list'

function NodeCounts({ node }: { node: LibraryNode }) {
  return node.summary ? <div className="group-data-[view=list]:m-0 max-[767px]:group-data-[view=list]:col-start-2 max-[767px]:group-data-[view=list]:row-[1/4] flex flex-wrap items-center gap-4 text-[11px] leading-normal [&_>_span]:inline-flex [&_>_span]:items-center [&_>_span]:gap-1.5 [&_svg]:size-2.5"><span><StatusShape state="due" />{node.summary.due} Due</span><span><StatusShape state="new" />{node.summary.new} New</span></div> : <span className="text-muted-foreground text-xs leading-normal mt-1">Unavailable</span>
}

function NodeItem({ node, view, space, parentId }: { node: LibraryNode; view: ViewMode; space: 'PERSONAL' | 'PUBLISHED'; parentId: string }) {
  const folder = libraryNodeKind(node) === 'FOLDER'
  const detail = folder ? `${node.type === 'REFERENCE' ? 'Folder reference · ' : ''}${node.summary ? `${node.summary.reachable_decks} ${node.summary.reachable_decks === 1 ? 'deck' : 'decks'} · ${node.summary.total} words` : 'Summary unavailable'}`
    : `${libraryNodeLabel(node)}${node.summary ? ` · ${node.summary.total} words` : ''}`
  return <li className="library-node-item relative min-w-0 border border-border bg-background transition-colors hover:bg-accent focus-within:bg-accent group-data-[view=list]:border-0 group-data-[view=list]:border-b group-data-[view=list]:border-border" data-view={view}>
    <Link href={space === 'PUBLISHED' ? publishedHref(node.owner_id ?? 'me', node.id) : libraryHref(node.id)} className="relative flex min-h-[164px] items-start gap-3 overflow-hidden py-[18px] pr-11 pb-[34px] pl-[18px] focus-visible:outline-2 focus-visible:-outline-offset-[3px] focus-visible:outline-ring [&>.bauhaus-icon]:size-7 [&>.bauhaus-icon]:shrink-0 group-data-[view=list]:min-h-[74px] group-data-[view=list]:items-center group-data-[view=list]:py-3 group-data-[view=list]:pr-[54px] group-data-[view=list]:pb-3 group-data-[view=list]:pl-[14px]" aria-label={`Open ${node.name}, ${libraryNodeLabel(node)}`}>
      <LibraryNodeIcon node={node} />
      <div className="relative z-[1] min-w-0 [&_h3]:text-[15px] [&_h3]:leading-[1.35] [&_h3]:wrap-anywhere [&_p]:my-[5px] [&_p]:mb-[7px] [&_p]:text-xs [&_p]:leading-[1.4] [&_p]:text-muted-foreground group-data-[view=list]:grid group-data-[view=list]:w-full group-data-[view=list]:grid-cols-[minmax(180px,1fr)_minmax(130px,.8fr)_minmax(120px,.7fr)_auto] group-data-[view=list]:items-center group-data-[view=list]:gap-4 group-data-[view=list]:[&_p]:m-0 max-[767px]:group-data-[view=list]:grid-cols-[minmax(0,1fr)_auto] max-[767px]:group-data-[view=list]:gap-x-[10px] max-[767px]:group-data-[view=list]:gap-y-[3px] max-[767px]:group-data-[view=list]:[&_p]:col-start-1"><h3>{node.name}</h3><p>{detail}</p><LibraryAuthor ownerId={node.owner_id} /><NodeCounts node={node} /></div>
      {view === 'cards' && <Motif name={libraryMotif(node.id)} data-motif={libraryMotif(node.id)} className="library-node-motif absolute right-0 bottom-0 w-[100px] h-[75px] opacity-85 pointer-events-none" />}
    </Link>
    <LibraryNodeActions node={node} space={space} parentId={parentId} />
  </li>
}

export function LibraryFolder({ nodeId, name, space, canCreate }: { nodeId: string; name: string; space: 'PERSONAL' | 'PUBLISHED'; canCreate: boolean }) {
  const account = useAccount()
  const [search, setSearch] = useState(''), q = useDeferredValue(search)
  const [cursors, setCursors] = useState<string[]>([])
  const [view, setView] = useState<ViewMode>('cards')
  const [creating, setCreating] = useState<'DECK' | 'FOLDER' | null>(null)
  useEffect(() => { setView(localStorage.getItem(viewKey) === 'list' ? 'list' : 'cards') }, [])
  const changeView = (next: ViewMode) => { setView(next); localStorage.setItem(viewKey, next) }
  const query = useLibraryContents(nodeId, { q, cursor: cursors.at(-1), limit: 12 })
  const nodes = query.data?.nodes ?? [], folders = nodes.filter(node => libraryNodeKind(node) === 'FOLDER'), decks = nodes.filter(node => libraryNodeKind(node) !== 'FOLDER')
  const searchChange = (value: string) => { setSearch(value); setCursors([]) }
  return <section className="[&_>_section_+_section]:mt-6" aria-label="Folder contents" aria-busy={query.isFetching || q !== search}>
    <div className="library-contents-toolbar flex justify-between items-center gap-4 mb-5 max-[767px]:items-stretch max-[767px]:flex-col"><LibrarySearch value={search} onChange={searchChange} label="Search this folder" />
      <div className="flex items-center gap-2 flex-wrap max-[767px]:justify-start">
        <div className="inline-flex gap-0.5 p-0.5 border border-border [&_[aria-pressed=true]]:bg-foreground [&_[aria-pressed=true]]:text-background" role="group" aria-label="View mode"><Button size="icon-sm" variant="ghost" aria-label="Card view" aria-pressed={view === 'cards'} onClick={() => changeView('cards')}><LayoutGrid aria-hidden="true" /></Button><Button size="icon-sm" variant="ghost" aria-label="List view" aria-pressed={view === 'list'} onClick={() => changeView('list')}><List aria-hidden="true" /></Button></div>
        {canCreate && <><Button variant="outline" size="sm" onClick={() => setCreating('FOLDER')}><Plus aria-hidden="true" />New folder</Button><Button size="sm" onClick={() => setCreating('DECK')}><Plus aria-hidden="true" />New deck</Button></>}
      </div>
    </div>
    {query.isError ? <HomeFailure label="folder contents" error={query.error} retry={() => { void query.refetch() }} /> : query.isPending ? <HomeLoading label="folder contents" />
      : nodes.length === 0 ? <LibraryEmpty title={q ? 'No matching content.' : 'This folder is empty.'} description={q ? undefined : 'Create a deck or folder to get started.'} reset={q ? () => searchChange('') : undefined} /> : <>
        {folders.length > 0 && <section aria-labelledby="library-subfolders-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-subfolders-title">{q ? 'Matching folders' : 'Subfolders'}</h2></div>
          <ul className="library-node-grid group grid grid-cols-3 gap-3 data-[view=list]:grid-cols-1 data-[view=list]:gap-0 data-[view=list]:border-t data-[view=list]:border-border max-[1199px]:grid-cols-2 max-[767px]:grid-cols-1" data-view={view}>{folders.map(node => <NodeItem key={node.id} node={node} view={view} space={space} parentId={nodeId} />)}</ul>
        </section>}
        {decks.length > 0 && <section aria-labelledby="library-decks-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-decks-title">{q ? 'Matching decks' : 'Decks'}</h2></div>
          <ul className="library-node-grid group grid grid-cols-3 gap-3 data-[view=list]:grid-cols-1 data-[view=list]:gap-0 data-[view=list]:border-t data-[view=list]:border-border max-[1199px]:grid-cols-2 max-[767px]:grid-cols-1" data-view={view}>{decks.map(node => <NodeItem key={node.id} node={node} view={view} space={space} parentId={nodeId} />)}</ul>
        </section>}
        {(query.data?.next_cursor || cursors.length > 0) && <LibraryPagination page={cursors.length + 1} busy={query.isFetching}
          previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={query.data?.next_cursor ? () => setCursors([...cursors, query.data!.next_cursor!]) : undefined} />}
      </>}
    {creating && account.profile && <LibraryNodeForm key={`${nodeId}:${creating}`} profile={account.profile} kind={creating} open onOpenChange={open => { if (!open) setCreating(null) }} parent={{ id: nodeId, name, space }} />}
  </section>
}
