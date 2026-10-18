'use client'

import { webConfig } from '@/config'

import { useHydrated } from '@/lib/use-hydrated.client'
import { usePathname, useSearchParams } from 'next/navigation'
import { meaningOptions } from '@/features/library/queries'
import { updateUrl, paginationHref } from '@/lib/query/url'

import { useDeferredValue, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ArrowUpRight, Plus } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Table, TableHeader, TableHead, TableBody, TableRow, TableCell } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectGroup, SelectItem } from '@/components/ui/select'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { HomeFailure, StatusShape } from '@/features/home/home-state.client'
import { LibraryTableSkeleton } from './library-skeletons'
import { useLibraryMeanings } from '@/features/library/use-library.client'
import { dateLabel, type Meaning, type MeaningFilter, type MeaningSort } from '@/features/library/model'
import { MarkedText } from '@/components/content/marked-text'
import { parseMarkedText } from '@/lib/marked-text'
import type { StudySummary } from '@/lib/api/study'
import { WordPickerDialog } from '@/features/vocabulary/word-picker-dialog.client'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useServices } from '@/lib/api/services/provider.client'
import { LearningBadge, LibraryEmpty, LibraryPagination, LibrarySearch } from './library-shared.client'
import { MeaningSources } from './meaning-sources.client'

export function LibraryWords({ nodeId, folder, editable, summary, timezone, publicRead = false }: { nodeId: string; folder: boolean; editable: boolean; summary?: StudySummary; timezone: string; publicRead?: boolean }) {
  const hydrated = useHydrated()
  const t = useTranslations('library')
  const { services, scope } = useServices(), queryClient = useQueryClient()
  const [pickerOpen, setPickerOpen] = useState(false)
  const pathname = usePathname() ?? '/'
  const params = useSearchParams(), options = meaningOptions(params)
  const search = params.get('q') ?? '', q = useDeferredValue(search.trim())
  const state = publicRead ? 'all' : options.state!, sort = publicRead ? 'lemma_asc' : options.sort!, cursors = params.getAll('cursor')
  const setState = (value: MeaningFilter) => updateUrl({ state: value === 'all' ? null : value, cursor: null })
  const setSort = (value: MeaningSort) => updateUrl({ sort: value === 'lemma_asc' ? null : value, cursor: null })
  const setCursors = (values: string[]) => updateUrl({ cursor: values })
  const [selected, setSelected] = useState<Meaning | null>(null)
  const [removing, setRemoving] = useState(false), [removeError, setRemoveError] = useState('')
  const trigger = useRef<number | null>(null)
  const query = useLibraryMeanings(nodeId, { q, state, sort, cursor: cursors.at(-1), limit: webConfig.pagination.library }, publicRead)
  const filtered = Boolean(q || state !== 'all')
  const searchChange = (value: string) => updateUrl({ q: value, cursor: null }, true)
  const clear = () => { searchChange(''); setState('all') }
  async function removeSense() {
    if (!selected) return
    setRemoving(true); setRemoveError('')
    try {
      await services.library.updateDeckSenses(nodeId, { add: [], remove: [selected.sense_id] }, new AbortController().signal)
      await invalidateLibrary(queryClient, services.mode, scope)
      setSelected(null)
      toast.success(t('meaningRemoved'))
    } catch (cause) { setRemoveError(cause instanceof Error ? cause.message : t('couldNotRemoveMeaning')) }
    finally { setRemoving(false) }
  }
  return <section className="library-meanings" aria-label={t('wordsInScope')} aria-busy={query.isFetching || q !== search}>
    <div className="flex flex-wrap items-center gap-3 mb-3"><LibrarySearch value={search} onChange={searchChange} label={t('searchWords')} />
      {!publicRead && <ToggleGroup type="single" value={state} onValueChange={value => { if (value) { setState(value as MeaningFilter) } }} aria-label={t('learningState')} className="library-state-filters flex-wrap [&_[data-slot=toggle-group-item]]:gap-1.5 [&_[data-slot=toggle-group-item]_>_span]:text-muted-foreground [&_[data-slot=toggle-group-item]_>_span]:text-[11px] [&_[data-slot=toggle-group-item]_>_span]:tabular-nums [&_[data-state=on]_>_span]:text-inherit [&_.home-status-shape]:size-3 max-[767px]:w-full">
        <ToggleGroupItem value="all" aria-label={t('allWordsWithCount', { count: summary?.total ?? '—' })}>{t('allWords')} <span>{summary?.total ?? '—'}</span></ToggleGroupItem>
        {([['due', t('due'), 'due', summary?.due ?? '—', t('dueWithCount', { count: summary?.due ?? '—' })], ['new', t('new'), 'new', summary?.new ?? '—', t('newWithCount', { count: summary?.new ?? '—' })], ['not_yet_due', t('notDue'), 'not-due', summary?.not_due ?? '—', t('notDueWithCount', { count: summary?.not_due ?? '—' })]] as const).map(([value, label, shape, count, aria]) =>
          <ToggleGroupItem key={value} value={value} aria-label={aria}><StatusShape state={shape} />{label}<span>{count}</span></ToggleGroupItem>)}
      </ToggleGroup>}
      <Select value={sort} onValueChange={value => { setSort(value as MeaningSort); setCursors([]) }}><SelectTrigger aria-label={t('sortWords')} className="w-[168px]"><SelectValue>{sort === 'last_reviewed_desc' ? t('lastReviewed') : t('wordAz')}</SelectValue></SelectTrigger>
        <SelectContent><SelectGroup><SelectItem value="lemma_asc">{t('wordAz')}</SelectItem>{!publicRead && <SelectItem value="last_reviewed_desc">{t('lastReviewed')}</SelectItem>}</SelectGroup></SelectContent>
      </Select>
      {editable && !folder && <Button variant="outline" onClick={() => setPickerOpen(true)}><Plus data-icon="inline-start" aria-hidden="true" />{t('addWords')}</Button>}
    </div>
    {query.isError ? <HomeFailure label={t('words').toLowerCase()} error={query.error} retry={() => { void query.refetch() }} /> : query.isPending ? <LibraryTableSkeleton rows={8} />
      : query.data.senses.length === 0 ? <LibraryEmpty title={filtered ? t('noMatchingWords') : t('noWordsHereYet')} description={!filtered && editable ? t('addWordsToDeckPrompt') : undefined} reset={filtered ? clear : undefined} />
        : <>
          <Table className={`${publicRead ? '[&_th:first-child]:w-[26%] [&_th:last-child]:w-[74%]' : '[&_th:first-child]:w-[19%] [&_th:nth-child(2)]:w-[52%] [&_th:last-child]:w-[14%]'} library-meaning-table table-fixed [&_th]:text-[11px] [&_th]:text-muted-foreground [&_td]:whitespace-normal [&_td]:wrap-anywhere [&_td]:text-[13px] [&_td]:py-2 max-[767px]:block max-[767px]:[&_tbody]:block max-[767px]:[&_thead]:sr-only max-[767px]:[&_tr]:grid max-[767px]:[&_tr]:grid-cols-[minmax(0,1fr)_auto] max-[767px]:[&_tr]:gap-x-3 max-[767px]:[&_tr]:gap-y-1.5 max-[767px]:[&_tr]:py-3 max-[767px]:[&_td]:block max-[767px]:[&_td]:p-0`}><caption className="sr-only">{t('wordsCaption', { kind: folder ? t('kindFolder') : t('kindDeck') })}</caption>
            <TableHeader><TableRow><TableHead>{t('word')}</TableHead><TableHead>{t('definition')}</TableHead>{!publicRead && <><TableHead>{t('status')}</TableHead><TableHead>{t('lastReviewed')}</TableHead></>}</TableRow></TableHeader>
            <TableBody>{query.data.senses.map(sense => <TableRow key={sense.sense_id}>
              <TableCell className="[&_[data-slot=button]]:inline-flex [&_[data-slot=button]]:p-0 [&_[data-slot=button]]:h-auto [&_[data-slot=button]]:min-h-7 [&_[data-slot=button]]:max-w-full [&_[data-slot=button]]:whitespace-normal [&_[data-slot=button]]:text-left [&_[data-slot=button]]:text-sm [&_[data-slot=button]]:font-bold [&_small]:inline [&_small]:text-[11px] [&_small]:text-muted-foreground [&_small]:ml-2 max-[767px]:col-start-1 max-[767px]:row-start-1 max-[767px]:[&_small]:block max-[767px]:[&_small]:ml-0"><Button disabled={!hydrated} data-sense-trigger={sense.sense_id} variant="link" onClick={() => { trigger.current = sense.sense_id; setRemoveError(''); setSelected(sense) }} aria-label={t('viewMeaningAria', { lemma: sense.lemma, definition: parseMarkedText(sense.definition ?? t('definitionUnavailable')).text })} aria-haspopup="dialog">{sense.lemma}</Button><small>{sense.pos}</small></TableCell>
              <TableCell className="library-definition-cell text-muted-foreground leading-normal max-[767px]:col-span-full max-[767px]:row-start-2"><MarkedText text={sense.definition ?? t('definitionUnavailable')} /></TableCell>
              {!publicRead && <><TableCell className="library-state-cell max-[767px]:col-start-2 max-[767px]:row-start-1">{sense.learning ? <LearningBadge state={sense.learning.state} /> : t('notAvailable')}</TableCell>
              <TableCell className="text-muted-foreground text-xs max-[767px]:col-span-full"><span className="hidden max-[767px]:inline">{t('lastReviewed')} </span>{dateLabel(sense.learning?.last_reviewed_at ?? null, timezone)}</TableCell></>}
            </TableRow>)}</TableBody>
          </Table>
          <LibraryPagination previousHref={cursors.length ? paginationHref(pathname, params, cursors.slice(0, -1)) : undefined} nextHref={query.data?.next_cursor ? paginationHref(pathname, params, [...cursors, query.data.next_cursor]) : undefined} page={cursors.length + 1} busy={query.isFetching} previous={cursors.length ? () => setCursors(cursors.slice(0, -1)) : undefined}
            next={query.data.next_cursor ? () => setCursors([...cursors, query.data.next_cursor!]) : undefined} />
        </>}
    {editable && !folder && <WordPickerDialog open={pickerOpen} onOpenChange={setPickerOpen} deckId={nodeId} />}
    <Sheet open={Boolean(selected)} onOpenChange={open => { if (!open) setSelected(null) }}>
      <SheetContent className="data-[slot=sheet-content]:w-[min(100%,480px)] data-[slot=sheet-content]:max-w-[480px] data-[slot=sheet-content]:overflow-y-auto [&_[data-slot=sheet-header]]:px-6 [&_[data-slot=sheet-header]]:pt-10 [&_[data-slot=sheet-header]]:pb-6 [&_[data-slot=sheet-header]]:border-b [&_[data-slot=sheet-header]]:border-border [&_[data-slot=sheet-title]]:text-[32px] [&_[data-slot=sheet-title]]:font-extrabold [&_[data-slot=sheet-title]]:tracking-tight [&_[data-slot=sheet-title]]:wrap-anywhere" onCloseAutoFocus={event => { event.preventDefault(); document.querySelector<HTMLButtonElement>(`button[data-sense-trigger="${trigger.current}"]`)?.focus({ preventScroll: true }) }}>
        {selected && <><SheetHeader><SheetTitle>{selected.lemma}</SheetTitle><SheetDescription>{selected.pos}{selected.cefr_level ? ` · ${selected.cefr_level}` : ''}</SheetDescription></SheetHeader>
          <div className="[&_dl_>_div]:flex [&_dl_>_div]:justify-between [&_dl_>_div]:gap-4 [&_dl_>_div]:py-3 [&_dl_>_div]:border-b [&_dl_>_div]:border-border [&_dl_>_div]:text-xs [&_dt]:text-muted-foreground [&_dd]:text-right px-6 pt-2 pb-8 [&_>_section]:my-8 [&_h3]:text-sm [&_h3]:font-bold [&_h3]:mb-3 [&_blockquote]:text-muted-foreground [&_blockquote]:text-sm [&_blockquote]:leading-relaxed [&_blockquote]:mt-3">{selected.learning && <LearningBadge state={selected.learning.state} />}<p className="text-xl leading-relaxed mt-5"><MarkedText text={selected.definition ?? t('definitionUnavailable')} /></p>
            {selected.examples.length > 0 && <section><h3>{t('examples')}</h3>{selected.examples.map((example, index) => <blockquote key={index}><MarkedText text={example.text} /></blockquote>)}</section>}
            {!publicRead && <section><h3>{t('review')}</h3><dl><div><dt>{t('lastReviewed')}</dt><dd>{dateLabel(selected.learning?.last_reviewed_at ?? null, timezone)}</dd></div><div><dt>{t('nextReview')}</dt><dd>{dateLabel(selected.learning?.due_at ?? null, timezone)}</dd></div></dl></section>}
            {!publicRead && <MeaningSources key={selected.sense_id} nodeId={nodeId} sense={selected} />}
            <Button asChild variant="outline"><Link href={`/dictionary?q=${encodeURIComponent(selected.lemma)}`}>{t('openInDictionary')}<ArrowUpRight data-icon="inline-end" aria-hidden="true" /></Link></Button>
            {editable && !folder && <><Button variant="outline" onClick={() => { void removeSense() }} disabled={removing}>{removing ? t('removing') : t('removeFromDeck')}</Button>{removeError && <p role="alert">{removeError}</p>}</>}
          </div></>}
      </SheetContent>
    </Sheet>
  </section>
}
