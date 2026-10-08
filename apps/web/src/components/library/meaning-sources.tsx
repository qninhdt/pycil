'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useInfiniteQuery } from '@tanstack/react-query'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'
import { nodeHref, type Meaning } from '@/lib/library-model'

export function MeaningSources({ nodeId, sense }: { nodeId: string; sense: Pick<Meaning, 'sense_id' | 'sources' | 'sources_has_more'> }) {
  const { services, scope } = useServices()
  const [expanded, setExpanded] = useState(false)
  const query = useInfiniteQuery({ queryKey: [services.mode, scope, 'meaning-sources', nodeId, sense.sense_id], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => services.library.sources(nodeId, sense.sense_id, pageParam, signal), getNextPageParam: page => page.next_cursor ?? undefined, enabled: expanded })
  const sources = [...new Map([...sense.sources, ...(query.data?.pages.flatMap(page => page.decks) ?? [])].map(source => [source.id, source])).values()]
  if (!sources.length && !sense.sources_has_more) return null
  return <section><h3>Source decks</h3><ul>{sources.map(source => <li key={source.id}><Button asChild variant="link"><Link href={nodeHref(source)}>{source.name}<ArrowUpRight data-icon="inline-end" aria-hidden="true" /></Link></Button></li>)}</ul>
    {expanded && query.isPending && <p role="status">Loading source decks…</p>}
    {query.isError ? <div role="alert"><p>Could not load source decks.</p><Button variant="link" onClick={() => { void query.refetch() }}>Retry</Button></div> : sense.sources_has_more && (!expanded || query.hasNextPage) && <Button variant="link" disabled={query.isFetching} onClick={() => { if (expanded) void query.fetchNextPage(); else setExpanded(true) }}>{query.isFetching ? 'Loading…' : 'Load more source decks'}</Button>}
  </section>
}
