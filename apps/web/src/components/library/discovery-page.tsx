'use client'

import { useDeferredValue, useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { useServices } from '@/lib/services/provider'
import { publishedHref } from '@/lib/library-model'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { NativeSelect } from '@/components/ui/native-select'
import { LibraryAuthor } from './library-author'
import { LibraryNodeIcon } from './library-node-icon'
import { LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared'

export function DiscoveryPage() {
  const t = useTranslations('library')
  const { services, scope } = useServices()
  const [search, setSearch] = useState(''), q = useDeferredValue(search)
  const [type, setType] = useState<'all' | 'folder' | 'deck'>('all')
  const [cursors, setCursors] = useState<string[]>([])
  const cursor = q === search ? cursors.at(-1) : undefined
  const query = useQuery({ queryKey: [services.mode, scope, 'discovery', q, type, cursor], queryFn: ({ signal }) => services.library.discovery({ q, type: type === 'all' ? undefined : type, cursor, limit: 12 }, signal) })
  return <div className="w-full min-w-0">
    <header className="py-6 border-b border-border"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold tracking-tight">{t('discoveryTitle')}<span className="text-art-red" aria-hidden="true">.</span></h1><p className="mt-2 text-sm text-muted-foreground">{t('discoveryDesc')}</p></header>
    <div className="flex flex-wrap gap-3 py-4"><LibrarySearch label={t('searchPublished')} value={search} onChange={value => { setSearch(value); setCursors([]) }} /><NativeSelect aria-label={t('materialType')} value={type} onChange={event => { setType(event.target.value as typeof type); setCursors([]) }}><option value="all">{t('allMaterial')}</option><option value="folder">{t('folders')}</option><option value="deck">{t('decks')}</option></NativeSelect></div>
    {query.isError ? <HomeFailure label={t('publishedMaterial').toLowerCase()} error={query.error} retry={() => { setCursors([]); void query.refetch() }} /> : query.isPending ? <HomeLoading label={t('publishedMaterial').toLowerCase()} /> : query.data.nodes.length === 0 ? <LibraryEmpty title={q ? t('noMatchingMaterial') : t('noPublishedMaterial')} reset={q || type !== 'all' ? () => { setSearch(''); setType('all'); setCursors([]) } : undefined} /> : <>
      <ul className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-2 max-[650px]:grid-cols-1" aria-label={t('publishedMaterial')}>{query.data.nodes.map(node => <li key={node.id} className="border border-border p-5 hover:bg-accent">
        <Link href={publishedHref(node.owner_id!, node.id)} className="flex items-start gap-3 focus-visible:outline-2 focus-visible:outline-ring"><LibraryNodeIcon node={node} /><span className="min-w-0"><strong className="block font-bold wrap-anywhere">{node.name}</strong><small className="block mt-1 text-muted-foreground">{node.type === 'folder' ? t('folder') : node.type === 'deck' ? t('deck') : t('reference')}</small>{node.description && <p className="mt-2 text-sm text-muted-foreground wrap-anywhere">{node.description}</p>}</span></Link>
        <div className="mt-3"><LibraryAuthor ownerId={node.owner_id} /></div>
      </li>)}</ul>
      <LibraryPagination page={cursors.length + 1} busy={query.isFetching || q !== search} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={query.data.next_cursor ? () => setCursors([...cursors, query.data.next_cursor!]) : undefined} />
    </>}
  </div>
}
