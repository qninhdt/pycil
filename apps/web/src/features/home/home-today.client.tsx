'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Plus, RotateCcw } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty'
import type { HomeResource } from '@/features/home/use-home.client'
import type { StudySummary } from '@/lib/api/study'
import { dayLabel } from '@/features/home/calendar'
import { HomeFailure, StatusShape } from './home-state.client'
import { TodaySkeleton } from './home-skeletons'

export function HomeToday({ summary, today }: { summary: HomeResource<StudySummary>; today: string | null }) {
  const t = useTranslations('home')
  const data = summary.data

  return <section aria-labelledby="home-today-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><div><h2 id="home-today-title">{t('today')}</h2>{today && <p><time dateTime={today}>{dayLabel(today, { weekday: 'long', month: 'short', day: 'numeric' })}</time></p>}</div>
      <Button variant="ghost" size="icon" onClick={summary.retry} disabled={summary.status === 'loading'} aria-label={t('refreshCounts')}><RotateCcw aria-hidden="true" /></Button></div>
    {summary.status === 'loading' ? <TodaySkeleton /> : summary.status === 'error' ? <HomeFailure label={t('libraryCounts')} error={summary.error} retry={summary.retry} />
      : data && data.total === 0 ? <Empty className="min-h-[196px]"><EmptyHeader><EmptyTitle>{t('todayEmptyTitle')}</EmptyTitle><EmptyDescription>{t('todayEmptyDesc')}</EmptyDescription></EmptyHeader>
        <EmptyContent><Button asChild size="lg"><Link href="/app/personal?create=deck"><Plus className="size-4 mr-2" aria-hidden="true" />{t('createDeck')}</Link></Button><Button asChild variant="link"><Link href="/discovery">{t('exploreDiscovery')}</Link></Button></EmptyContent></Empty>
      : data && <>
        <dl className="grid grid-cols-[1.2fr_1fr_1fr] gap-5 items-end my-7 [&_>_div]:min-w-0 [&_dt]:flex [&_dt]:items-center [&_dt]:gap-2 [&_dt]:text-[13px] [&_dt]:font-[650] [&_dd]:text-[clamp(30px,3.5vw,46px)] [&_dd]:font-extrabold [&_dd]:leading-none [&_dd]:tracking-tight [&_dd]:tabular-nums [&_dd]:my-4 [&_dd]:mb-2 [&_dd]:break-words [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground max-xl:gap-3 max-md:my-4 max-md:gap-2 max-md:grid-cols-3 max-md:[&_dt]:text-[11px] max-md:[&_dt]:gap-1 max-md:[&_dd]:text-[34px] max-md:[&_dd]:my-1.5 max-md:[&_p]:text-[11px] max-md:[&_p]:line-clamp-2">
          <div className="home-count-due [&_dd]:text-art-red [&_dd]:text-[clamp(52px,5vw,72px)] max-md:[&_dd]:text-[34px]"><dt><StatusShape state="due" />{t('dueNow')}</dt><dd>{data.due.toLocaleString('en')}</dd><p>{t('dueDesc')}</p></div>
          <div><dt><StatusShape state="new" />{t('new')}</dt><dd>{data.new.toLocaleString('en')}</dd><p>{t('newDesc')}</p></div>
          <div><dt><StatusShape state="not-due" />{t('notDue')}</dt><dd>{data.not_due.toLocaleString('en')}</dd><p>{t('notDueDesc')}</p></div>
        </dl>
        <div className="flex flex-wrap items-center gap-3 my-7 max-md:my-4 max-md:flex-col max-md:items-stretch max-md:gap-2.5 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-relaxed">
          {data.due > 0 ? <Button size="lg" variant="red" className="max-md:w-full" asChild><Link href={`/app/learn?node=${encodeURIComponent(data.node_id)}&selection=due`}>{t('startReview')}</Link></Button>
            : data.new > 0 ? <Button size="lg" variant="yellow" className="max-md:w-full" asChild><Link href={`/app/learn?node=${encodeURIComponent(data.node_id)}&selection=new`}>{t('learnNew')}</Link></Button>
            : <Button size="lg" className="max-md:w-full" asChild><Link href={`/app/learn?node=${encodeURIComponent(data.node_id)}&selection=auto`}>{t('practice')}</Link></Button>}
          {data.due > 0 && data.new > 0 && <Button size="lg" variant="outline" className="max-md:w-full" asChild><Link href={`/app/learn?node=${encodeURIComponent(data.node_id)}&selection=new`}>{t('learnNew')}</Link></Button>}
          {data.due === 0 && <p className="max-md:text-center">{t('noReviewsDue')}. {data.new > 0 ? t('makeRoomNew') : t('practiceEarlyOrReturn')}</p>}
        </div>
        <div className="pt-[18px] border-t border-border [&_p]:flex [&_p]:flex-wrap [&_p]:items-baseline [&_p]:gap-1 [&_p]:text-xs [&_strong]:font-extrabold">
          <p><strong>{data.total.toLocaleString('en')}</strong> {t('meaningsInLibrary')}</p>
          <div className="home-status-band h-1.5 flex w-full mt-3 [&_>_span]:basis-0 [&_[data-status=due]]:bg-art-red [&_[data-status=new]]:bg-art-yellow [&_[data-status=not-due]]:bg-art-blue" role="img" aria-label={t('statusBandAria', { due: data.due, new: data.new, notDue: data.not_due, total: data.total })}>
            {([['due', data.due], ['new', data.new], ['not-due', data.not_due]] as const).map(([state, count]) => count > 0 && <span key={state} data-status={state} style={{ flexGrow: count }} />)}
          </div>
        </div>
      </>}
  </section>
}
