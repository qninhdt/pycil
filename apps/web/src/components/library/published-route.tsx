'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/components/application/providers'
import { PublicProfilePage } from '@/components/account/public-profile-page'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { useServices } from '@/lib/services/provider'
import { publishedHref, type LibraryTab } from '@/lib/library-model'
import { LibraryPage } from './library-page'
import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { isDeck } from '@/lib/library-model'
import { MarkedText } from '@/components/content/marked-text'
import { LibraryHeader } from './library-header'
import { LibraryEmpty, LibraryPagination } from './library-shared'

function PublicNodeView({ nodeId }: { nodeId: string }) {
  const { services, scope } = useServices()
  const t = useTranslations('library')
  const [cursors, setCursors] = useState<string[]>([])
  const node = useQuery({ queryKey: [services.mode, scope, 'public-node', nodeId], queryFn: ({ signal }) => services.library.publicNode(nodeId, signal) })
  const deck = node.data ? isDeck(node.data) : false
  const words = useQuery({ queryKey: [services.mode, scope, 'public-meanings', nodeId, cursors.at(-1)], queryFn: ({ signal }) => services.library.publicMeanings(nodeId, cursors.at(-1), signal), enabled: !!node.data && deck })
  const contents = useQuery({ queryKey: [services.mode, scope, 'public-contents', nodeId, cursors.at(-1)], queryFn: ({ signal }) => services.library.publicContents(nodeId, cursors.at(-1), signal), enabled: !!node.data && !deck })
  if (node.isPending) return <HomeLoading label="Published material" />
  if (node.isError) return <HomeFailure label="Published material" error={node.error} retry={() => { void node.refetch() }} />
  const page = deck ? words : contents
  const cursor = page.data?.next_cursor
  return <div className="library-page w-full">
    <LibraryHeader node={node.data} profile={null} editable={false} />
    <section className="py-5" aria-label={deck ? t('words') : t('folderContents')}>
      {page.isPending ? <HomeLoading label="Published material" /> : page.isError ? <HomeFailure label="Published material" error={page.error} retry={() => { void page.refetch() }} />
        : deck ? words.data?.senses.length ? <ul className="divide-y divide-border">{words.data.senses.map(sense => <li key={sense.sense_id} className="py-4"><Link className="font-bold underline" href={`/app/dictionary?q=${encodeURIComponent(sense.lemma)}`}>{sense.lemma}</Link><small className="ml-2 text-muted-foreground">{sense.pos}</small><p className="mt-2"><MarkedText text={sense.definition ?? t('definitionUnavailable')} /></p>{sense.examples.map((example, index) => <blockquote key={index} className="mt-2 text-muted-foreground"><MarkedText text={example.text} /></blockquote>)}</li>)}</ul> : <LibraryEmpty title={t('noWordsToPreview')} />
          : <ul className="divide-y divide-border">{contents.data?.nodes.map(item => <li key={item.id} className="py-4"><Link className="font-bold underline" href={publishedHref(item.owner_id ?? node.data.owner_id, item.id)}>{item.name}</Link></li>)}</ul>}
      <LibraryPagination page={cursors.length + 1} busy={page.isFetching} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined} next={cursor ? () => setCursors([...cursors, cursor]) : undefined} />
    </section>
  </div>
}

export function PublishedRoute({ identifier, nodeId, tab }: { identifier: string; nodeId?: string; tab?: LibraryTab }) {
  const account = useAccount()
  const { services, scope } = useServices()
  const own = !!account.profile && (identifier === 'me' || identifier === account.profile.id || identifier === account.profile.handle)
  const owner = identifier === 'me' ? account.profile?.id : identifier
  const query = useQuery({ queryKey: [services.mode, scope, 'public-profile', owner], queryFn: ({ signal }) => services.account.publicProfile(owner!, signal), enabled: !!owner && !own })
  if (account.status === 'loading') return <HomeLoading label="your account" />
  if (own) return <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId ?? account.profile!.published_node_id} tab={tab} />
  if (!owner) return <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId} tab={tab} />
  if (query.isPending) return <HomeLoading label="Published library" />
  if (query.isError) return <HomeFailure label="Published library" error={query.error} retry={() => { void query.refetch() }} />
  if (nodeId) return account.profile ? <LibraryPage routeSpace="PUBLISHED" nodeId={nodeId} tab={tab} /> : <PublicNodeView key={nodeId} nodeId={nodeId} />
  return <PublicProfilePage identifier={owner} publishedBase={publishedHref(query.data.id)} />
}
