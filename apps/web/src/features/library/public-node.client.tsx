'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/features/account/account.client'
import { HomeFailure, HomeLoading } from '@/features/home/home-state.client'
import { useServices } from '@/lib/api/services/provider.client'
import { publicCollectionHref } from '@/features/library/model'
import { publicNodeQuery, publicMeaningsQuery, publicContentsQuery } from '@/features/library/public-queries'
import { updateUrl } from '@/lib/query/url'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { isDeck } from '@/features/library/model'
import { MarkedText } from '@/components/content/marked-text'
import { PublicCollectionActions } from './public-collection-actions.client'
import { LibraryHeader } from './library-header.client'
import { LibraryEmpty, LibraryPagination } from './library-shared.client'

export function PublicNodeView({ identifier, nodeId }: { identifier?: string; nodeId: string }) {
  const { services, scope } = useServices(), account = useAccount()
  const t = useTranslations('library')
  const params = useSearchParams(), cursors = params.getAll('cursor')
  const setCursors = (values: string[]) => updateUrl({ cursor: values })
  const node = useQuery(publicNodeQuery(services, scope, nodeId))
  const deck = node.data ? isDeck(node.data) : false
  const words = useQuery({ ...publicMeaningsQuery(services, scope, nodeId, cursors.at(-1)), enabled: !!node.data && deck && node.data.reference_available !== false })
  const contents = useQuery({ ...publicContentsQuery(services, scope, node.data?.target?.id ?? nodeId, cursors.at(-1)), enabled: !!node.data && !deck && node.data.reference_available !== false })
  if (node.isPending) return <HomeLoading label="Published material" />
  if (node.isError) return <HomeFailure label="Published material" error={node.error} retry={() => { void node.refetch() }} />
  const page = deck ? words : contents
  const cursor = page.data?.next_cursor
  return <div className="library-page w-full">
    <LibraryHeader node={node.data} profile={account.profile} editable={node.data.owner_id === account.profile?.id && node.data.role === 'normal'} />
    <PublicCollectionActions nodeId={nodeId} name={node.data.name} ownerId={node.data.owner_id} targetId={node.data.target?.id} />
    <section className="py-5" aria-label={deck ? t('words') : t('folderContents')}>
      {node.data.reference_available === false ? <LibraryEmpty title={t('referenceUnavailable')} /> : page.isPending ? <HomeLoading label="Published material" /> : page.isError ? <HomeFailure label="Published material" error={page.error} retry={() => { void page.refetch() }} />
        : deck ? words.data?.senses.length ? <ul className="divide-y divide-border">{words.data.senses.map(sense => <li key={sense.sense_id} className="py-4"><Link className="font-bold underline" href={`/app/dictionary?q=${encodeURIComponent(sense.lemma)}`}>{sense.lemma}</Link><small className="ml-2 text-muted-foreground">{sense.pos}</small><p className="mt-2"><MarkedText text={sense.definition ?? t('definitionUnavailable')} /></p>{sense.examples.map((example, index) => <blockquote key={index} className="mt-2 text-muted-foreground"><MarkedText text={example.text} /></blockquote>)}</li>)}</ul> : <LibraryEmpty title={t('noWordsToPreview')} />
          : <ul className="divide-y divide-border">{contents.data?.nodes.map(item => <li key={item.id} className="py-4"><Link className="font-bold underline" href={identifier ? `/u/${encodeURIComponent(identifier)}/${encodeURIComponent(item.id)}` : publicCollectionHref(item.owner_id ?? node.data.owner_id, item.id)}>{item.name}</Link></li>)}</ul>}
      <LibraryPagination page={cursors.length + 1} busy={page.isFetching} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={cursor ? () => setCursors([...cursors, cursor]) : undefined} />
    </section>
  </div>
}
