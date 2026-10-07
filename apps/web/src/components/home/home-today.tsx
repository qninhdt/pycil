'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ArrowRight, RotateCcw } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import type { HomeResource } from '@/hooks/use-learning'
import type { StudySummary, SessionSelection } from '@/lib/home-api'
import { dayLabel } from '@/lib/home-calendar'
import { HomeFailure, HomeLoading, StatusShape } from './home-state'
import { HomeSession } from './home-session'

export function HomeToday({ summary, today }: { summary: HomeResource<StudySummary>; today: string | null }) {
  const [selection, setSelection] = useState<SessionSelection | null>(null)
  const data = summary.data
  return <section aria-labelledby="home-today-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><div><h2 id="home-today-title">Today</h2>{today && <p><time dateTime={today}>{dayLabel(today, { weekday: 'long', month: 'short', day: 'numeric' })}</time></p>}</div>
      <Button variant="ghost" size="icon" onClick={summary.retry} disabled={summary.status === 'loading'} aria-label="Refresh Library counts"><RotateCcw aria-hidden="true" /></Button></div>
    {summary.status === 'loading' ? <HomeLoading label="Library counts" /> : summary.status === 'error' ? <HomeFailure label="Library counts" error={summary.error} retry={summary.retry} />
      : data && data.total === 0 ? <Empty className="min-h-[196px]"><EmptyHeader><EmptyTitle>Your Library starts here.</EmptyTitle><EmptyDescription>Add meanings to a deck, or save published material from Discovery. Your review counts will appear here.</EmptyDescription></EmptyHeader>
        <EmptyContent><Button asChild size="lg"><Link href="/app/personal?create=deck">Create a deck<ArrowRight data-icon="inline-end" aria-hidden="true" /></Link></Button><Button asChild variant="link"><Link href="/app/discovery">Explore Discovery</Link></Button></EmptyContent></Empty>
      : data && <>
        <dl className="grid grid-cols-[1.2fr_1fr_1fr] gap-5 items-end my-7 [&_>_div]:min-w-0 [&_dt]:flex [&_dt]:items-center [&_dt]:gap-2 [&_dt]:text-[13px] [&_dt]:font-[650] [&_dd]:text-[clamp(30px,3.5vw,46px)] [&_dd]:font-extrabold [&_dd]:leading-none [&_dd]:tracking-tight [&_dd]:tabular-nums [&_dd]:my-4 [&_dd]:mb-2 [&_dd]:break-words [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground max-xl:gap-3 max-md:gap-2.5 max-md:grid-cols-[1.15fr_1fr_1fr] max-md:[&_dt]:text-[11px] max-md:[&_dt]:gap-1.5 max-md:[&_dd]:text-[30px] max-md:[&_p]:text-[11px] max-[380px]:grid-cols-3 max-[380px]:[&_dt]:flex-wrap">
          <div className="home-count-due [&_dd]:text-art-red [&_dd]:text-[clamp(52px,5vw,72px)] max-md:[&_dd]:text-[52px]"><dt><StatusShape state="due" />Due now</dt><dd>{data.due.toLocaleString('en')}</dd><p>meanings to review</p></div>
          <div><dt><StatusShape state="new" />New</dt><dd>{data.new.toLocaleString('en')}</dd><p>not studied yet</p></div>
          <div><dt><StatusShape state="not-due" />Not yet due</dt><dd>{data.not_due.toLocaleString('en')}</dd><p>scheduled for later</p></div>
        </dl>
        <div className="flex flex-wrap items-center gap-3 my-7 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-relaxed max-[380px]:[&_>_[data-slot=button]]:w-full">
          {data.due > 0 ? <Button size="lg" variant="red" onClick={() => setSelection('DUE')}>Start review<ArrowRight data-icon="inline-end" aria-hidden="true" /></Button>
            : data.new > 0 ? <Button size="lg" variant="yellow" onClick={() => setSelection('NEW')}>Learn new<ArrowRight data-icon="inline-end" aria-hidden="true" /></Button>
            : <Button size="lg" onClick={() => setSelection('AUTO')}>Practice<ArrowRight data-icon="inline-end" aria-hidden="true" /></Button>}
          {data.due > 0 && data.new > 0 && <Button size="lg" variant="outline" onClick={() => setSelection('NEW')}>Learn new<ArrowRight data-icon="inline-end" aria-hidden="true" /></Button>}
          {data.due === 0 && <p>No reviews due right now.<br />{data.new > 0 ? 'Make room for something new.' : 'Practice early, or come back when a review is due.'}</p>}
        </div>
        {selection && <HomeSession key={selection} nodeId={data.node_id} selection={selection} close={() => setSelection(null)} />}
        <div className="pt-[18px] border-t border-border [&_p]:flex [&_p]:flex-wrap [&_p]:items-baseline [&_p]:gap-1 [&_p]:text-xs [&_strong]:font-extrabold">
          <p><strong>{data.total.toLocaleString('en')}</strong> meanings in your Library</p>
          <div className="home-status-band h-1.5 flex w-full mt-3 [&_>_span]:basis-0 [&_[data-status=due]]:bg-art-red [&_[data-status=new]]:bg-art-yellow [&_[data-status=not-due]]:bg-art-blue" role="img" aria-label={`${data.due} due, ${data.new} new, ${data.not_due} not yet due; ${data.total} total meanings`}>
            {([['due', data.due], ['new', data.new], ['not-due', data.not_due]] as const).map(([state, count]) => count > 0 && <span key={state} data-status={state} style={{ flexGrow: count }} />)}
          </div>
        </div>
      </>}
  </section>
}
