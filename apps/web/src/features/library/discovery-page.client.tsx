'use client'

import { useDeferredValue } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { updateUrl } from '@/lib/query/url'
import { discoveryQuery, discoveryState } from '@/features/library/discovery-queries'
import { useQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { useServices } from '@/lib/api/services/provider.client'
import { publicCollectionHref } from '@/features/library/model'
import { HomeFailure } from '@/features/home/home-state.client'
import { LibraryCardGridSkeleton } from './library-skeletons'
import { Motif } from '@/components/artwork/artwork'
import { NativeSelect } from '@/components/ui/native-select'
import { LibraryAuthor } from './library-author.client'
import { LibraryNodeIcon } from './library-node-icon'
import { LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared.client'

export function DiscoveryPage() {
  const t = useTranslations('library')
  const { services, scope } = useServices()
  const params = useSearchParams(), state = discoveryState(params)
  const search = params.get('q') ?? '', q = useDeferredValue(search.trim()), type = state.type, cursors = params.getAll('cursor')
  const cursor = q === search.trim() ? cursors.at(-1) : undefined
  const setSearch = (value: string) => updateUrl({ q: value, cursor: null }, true)
  const setType = (value: typeof type) => updateUrl({ type: value === 'all' ? null : value, cursor: null })
  const setCursors = (values: string[]) => updateUrl({ cursor: values })
  const query = useQuery(discoveryQuery(services, scope, { q, type, cursor }))
  return <div className="w-full min-w-0">
    <header className="grid grid-cols-[minmax(0,3fr)_1fr] border-b border-border"><div className="py-6 pr-6"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold tracking-tight">{t('discoveryTitle')}<span className="text-art-red" aria-hidden="true">.</span></h1><p className="mt-2 text-sm text-muted-foreground">{t('discoveryDesc')}</p></div><div className="header-motif-art max-md:hidden" aria-hidden="true"><Motif name="split-circle" /></div></header>
    <div className="flex flex-wrap gap-3 py-4"><LibrarySearch label={t('searchPublished')} value={search} onChange={value => { setSearch(value) }} /><NativeSelect aria-label={t('materialType')} value={type} onChange={event => { setType(event.target.value as typeof type) }}><option value="all">{t('allMaterial')}</option><option value="folder">{t('folders')}</option><option value="deck">{t('decks')}</option></NativeSelect></div>
    {query.isError ? <HomeFailure label={t('publishedMaterial').toLowerCase()} error={query.error} retry={() => { setCursors([]); void query.refetch() }} /> : query.isPending ? <LibraryCardGridSkeleton count={6} /> : query.data.nodes.length === 0 ? <LibraryEmpty title={q ? t('noMatchingMaterial') : t('noPublishedMaterial')} reset={q || type !== 'all' ? () => { setSearch(''); setType('all'); setCursors([]) } : undefined} /> : <>
      <ul className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-2 max-[650px]:grid-cols-1" aria-label={t('publishedMaterial')}>{query.data.nodes.map(node => <li key={node.id} className="border border-border p-5 hover:bg-accent">
        <Link href={publicCollectionHref(node.owner_id!, node.id)} className="flex items-start gap-3 focus-visible:outline-2 focus-visible:outline-ring"><LibraryNodeIcon node={node} /><span className="min-w-0"><strong className="block font-bold wrap-anywhere">{node.name}</strong><small className="block mt-1 text-muted-foreground">{node.type === 'folder' ? t('folder') : node.type === 'deck' ? t('deck') : t('reference')}</small>{node.description && <p className="mt-2 text-sm text-muted-foreground wrap-anywhere">{node.description}</p>}</span></Link>
        <div className="mt-3"><LibraryAuthor ownerId={node.owner_id} /></div>
      </li>)}</ul>
      <LibraryPagination page={cursors.length + 1} busy={query.isFetching || q !== search} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={query.data.next_cursor ? () => setCursors([...cursors, query.data.next_cursor!]) : undefined} />
    </>}
  </div>
}
