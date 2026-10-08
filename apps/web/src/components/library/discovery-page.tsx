'use client'

import { useDeferredValue, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/services/provider'
import { publishedHref } from '@/lib/library-model'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { NativeSelect } from '@/components/ui/native-select'
import { LibraryAuthor } from './library-author'
import { LibraryNodeIcon } from './library-node-icon'
import { LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared'

export function DiscoveryPage() {
  const { services, scope } = useServices()
  const [search, setSearch] = useState(''), q = useDeferredValue(search)
  const [type, setType] = useState<'ALL' | 'FOLDER' | 'DECK'>('ALL')
  const [cursors, setCursors] = useState<string[]>([])
  const cursor = q === search ? cursors.at(-1) : undefined
  const query = useQuery({ queryKey: [services.mode, scope, 'discovery', q, type, cursor], queryFn: ({ signal }) => services.library.discovery({ q, type: type === 'ALL' ? undefined : type, cursor, limit: 12 }, signal) })
  return <div className="w-full min-w-0">
    <header className="py-6 border-b border-border"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold tracking-tight">Discovery<span className="text-art-red" aria-hidden="true">.</span></h1><p className="mt-2 text-sm text-muted-foreground">Explore vocabulary other learners have published.</p></header>
    <div className="flex flex-wrap gap-3 py-4"><LibrarySearch label="Search published material" value={search} onChange={value => { setSearch(value); setCursors([]) }} /><NativeSelect aria-label="Material type" value={type} onChange={event => { setType(event.target.value as typeof type); setCursors([]) }}><option value="ALL">All material</option><option value="FOLDER">Folders</option><option value="DECK">Decks</option></NativeSelect></div>
    {query.isError ? <HomeFailure label="published material" error={query.error} retry={() => { setCursors([]); void query.refetch() }} /> : query.isPending ? <HomeLoading label="published material" /> : query.data.nodes.length === 0 ? <LibraryEmpty title={q ? 'No matching material.' : 'No published material yet.'} reset={q || type !== 'ALL' ? () => { setSearch(''); setType('ALL'); setCursors([]) } : undefined} /> : <>
      <ul className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-2 max-[650px]:grid-cols-1" aria-label="Published material">{query.data.nodes.map(node => <li key={node.id} className="border border-border p-5 hover:bg-accent">
        <Link href={publishedHref(node.owner_id!, node.id)} className="flex items-start gap-3 focus-visible:outline-2 focus-visible:outline-ring"><LibraryNodeIcon node={node} /><span className="min-w-0"><strong className="block font-bold wrap-anywhere">{node.name}</strong><small className="block mt-1 text-muted-foreground">{node.type === 'FOLDER' ? 'Folder' : node.type === 'DECK' ? 'Deck' : 'Reference'}</small>{node.description && <p className="mt-2 text-sm text-muted-foreground wrap-anywhere">{node.description}</p>}</span></Link>
        <div className="mt-3"><LibraryAuthor ownerId={node.owner_id} /></div>
      </li>)}</ul>
      <LibraryPagination page={cursors.length + 1} busy={query.isFetching || q !== search} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={query.data.next_cursor ? () => setCursors([...cursors, query.data.next_cursor!]) : undefined} />
    </>}
  </div>
}
