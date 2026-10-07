import { StatusShape } from '@/components/home/home-state'
import type { StudySummary } from '@/lib/home-api'

export function LibrarySummary({ summary }: { summary: StudySummary }) {
  return <section className="library-summary grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 border-b border-border items-stretch" aria-label="Learning counts">
    <div className="min-w-0 py-4 pr-6 max-xl:pr-4 max-[767px]:pr-0 max-[767px]:border-b max-[767px]:border-border [&_p]:flex [&_p]:flex-wrap [&_p]:gap-3 [&_p]:items-baseline [&_strong]:text-4xl [&_strong]:font-extrabold [&_strong]:leading-none [&_strong]:tracking-tight [&_strong]:tabular-nums [&_p_>_span]:text-sm [&_p_>_span]:text-muted-foreground max-[767px]:[&_strong]:text-4xl">
      <p><strong>{summary.total.toLocaleString('en')}</strong><span>words</span></p>
      <div className="forced-colors:[&>span]:border forced-colors:[&>span]:border-[CanvasText] flex h-1.5 mt-3 bg-secondary [&_>_span]:basis-0 [&_[data-status=due]]:bg-art-red [&_[data-status=new]]:bg-art-yellow [&_[data-status=not-due]]:bg-art-blue" role="img" aria-label={`${summary.due} due, ${summary.new} new, ${summary.not_due} not yet due; ${summary.total} total words`}>
        {([['due', summary.due], ['new', summary.new], ['not-due', summary.not_due]] as const).map(([state, count]) => count > 0 && <span key={state} data-status={state} style={{ flexGrow: count }} />)}
      </div>
    </div>
    <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden">
      <dl><dt className="flex items-center gap-2 text-[13px] leading-normal"><StatusShape state="due" />Due</dt><dd className="text-[26px] font-extrabold leading-none mt-2 tabular-nums">{summary.due.toLocaleString('en')}</dd></dl>
    </div>
    <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden">
      <dl><dt className="flex items-center gap-2 text-[13px] leading-normal"><StatusShape state="new" />New</dt><dd className="text-[26px] font-extrabold leading-none mt-2 tabular-nums">{summary.new.toLocaleString('en')}</dd></dl>
    </div>
    <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden">
      <dl><dt className="flex items-center gap-2 text-[13px] leading-normal"><StatusShape state="not-due" />Not yet due</dt><dd className="text-[26px] font-extrabold leading-none mt-2 tabular-nums">{summary.not_due.toLocaleString('en')}</dd></dl>
    </div>
    <dl className="hidden max-[767px]:grid max-[767px]:grid-cols-3 [&_>_div]:py-3 [&_>_div]:pl-2 [&_>_div:not(:first-child)]:border-l [&_>_div]:border-border [&_dt]:flex [&_dt]:items-center [&_dt]:gap-1.5 [&_dt]:text-xs [&_dt]:leading-normal [&_.home-status-shape]:size-3 [&_dd]:text-[22px] [&_dd]:font-extrabold [&_dd]:leading-none [&_dd]:mt-1.5 [&_dd]:tabular-nums">
      <div><dt><StatusShape state="due" />Due</dt><dd>{summary.due.toLocaleString('en')}</dd></div>
      <div><dt><StatusShape state="new" />New</dt><dd>{summary.new.toLocaleString('en')}</dd></div>
      <div><dt><StatusShape state="not-due" />Not yet due</dt><dd>{summary.not_due.toLocaleString('en')}</dd></div>
    </dl>
  </section>
}
