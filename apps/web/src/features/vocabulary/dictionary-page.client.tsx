'use client'

import { useHydrated } from '@/lib/use-hydrated.client'
import { useSearchParams } from 'next/navigation'
import { dictionaryQueries, dictionaryState } from '@/features/vocabulary/queries'
import { updateUrl } from '@/lib/query/url'

import { useDeferredValue, useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search, X } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Motif, Icon } from '@/components/artwork/artwork'
import { useAccount } from '@/features/account/account.client'
import { MarkedText } from '@/components/content/marked-text'
import { HomeFailure, HomeLoading } from '@/features/home/home-state.client'
import { LibraryDestinationDialog } from '@/features/library/library-destination-dialog.client'
import { MeaningSources } from '@/features/library/meaning-sources.client'
import { LearningBadge } from '@/features/library/library-shared.client'
import { PatternList } from './pattern-badge.client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { ReferenceHit, DictionaryWord, SenseContext } from '@/lib/api/vocabulary'
import { nodeHref } from '@/features/library/model'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useServices } from '@/lib/api/services/provider.client'
import { useAssistantView } from '@/features/assistant/current-view.client'

const label = (value: string) => value.toLowerCase().replaceAll('_', ' ')

export function WordDetail({ word, contexts, contextError, retryContext, onAdd, onSelectWord }: {
  word: DictionaryWord; contexts?: SenseContext[]; contextError?: Error | null; retryContext: () => void; onAdd: (id: number) => void; onSelectWord: (id: number, lemma: string) => void
}) {
  const account = useAccount()
  const t = useTranslations('dictionary')
  const tHome = useTranslations('home')
  const tCommon = useTranslations('common')
  const groups = [...new Set(word.senses.map(sense => sense.pos))]
  const [active, setActive] = useState(groups[0] ?? '')
  const visible = groups.length > 1 ? word.senses.filter(sense => sense.pos === active) : word.senses
  const context = new Map(contexts?.map(sense => [sense.sense_id, sense]) ?? [])
  const decks = [...(contexts ?? []).reduce((items, sense) => {
    for (const deck of sense.decks) items.set(deck.id, { ...deck, count: (items.get(deck.id)?.count ?? 0) + 1 })
    return items
  }, new Map<string, SenseContext['decks'][number] & { count: number }>()).values()]
  const deckCountsPartial = contexts?.some(sense => sense.decks_has_more) ?? false
  const studied = contexts?.filter(sense => sense.learning.state !== 'new').length ?? 0
  const pronunciation = word.senses.find(sense => sense.ipa_uk || sense.ipa_us)
  return <div className="grid grid-cols-[minmax(0,7fr)_minmax(230px,3fr)] border-b border-border max-[1000px]:grid-cols-1">
    <article className="min-w-0 pr-6.5 pt-6.5 pb-8 max-[1000px]:pr-0"><header className="flex justify-between gap-4 items-start mb-4.5 [&_h2]:text-[clamp(36px,4vw,56px)] [&_h2]:leading-[1.1] [&_h2]:wrap-anywhere max-[700px]:[&_h2]:text-[38px]"><div>
      <h2>{word.lemma}</h2><div className="flex flex-wrap gap-3 mt-2 text-muted-foreground text-sm">{pronunciation?.ipa_uk && <span>UK {pronunciation.ipa_uk}</span>}{pronunciation?.ipa_us && <span>US {pronunciation.ipa_us}</span>}</div>
      {word.aliases.length > 0 && <p className="mt-1 text-muted-foreground text-xs">{t('alsoSpelled', { aliases: word.aliases.join(', ') })}</p>}
    </div><span className="mt-2.5 capitalize text-[11px] tracking-widest">{label(word.type)} · {word.senses.length} {word.senses.length === 1 ? t('senseCount') : t('sensesCount')}</span></header>
      {groups.length > 1 && <Tabs value={active} onValueChange={setActive} className="mb-3 [&_[data-slot=tabs-list]]:w-full [&_[data-slot=tabs-list]]:justify-start  [&_[data-slot=tabs-trigger]]:capitalize [&_[data-slot=tabs-trigger]_span]:ml-1.5 [&_[data-slot=tabs-trigger]_span]:text-muted-foreground [&_[data-slot=tabs-trigger]_span]:text-[11px]"><TabsList aria-label={t('partOfSpeech')}>{groups.map(pos => <TabsTrigger key={pos} value={pos}>{label(pos)} <span>{word.senses.filter(sense => sense.pos === pos).length}</span></TabsTrigger>)}</TabsList></Tabs>}
      <div className="dictionary-senses">{visible.map((sense, index) => {
        const personal = context.get(sense.id)
        return <section key={sense.id} id={`sense-${sense.id}`} className="grid grid-cols-[48px_minmax(0,1fr)_auto] gap-4 py-5 border-t border-border scroll-mt-7 max-[700px]:grid-cols-[36px_minmax(0,1fr)] max-[700px]:gap-2.5">
          <span className="text-[23px] font-bold tabular-nums text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
            <div className="dictionary-sense-body"><div className="flex items-start flex-wrap gap-2.5 [&_h3]:text-[17px] [&_h3]:leading-normal [&_h3]:max-w-[65ch] [&_[data-slot=badge]]:flex-none"><h3>{sense.definition ? <MarkedText text={typeof sense.definition === 'string' ? sense.definition : sense.definition.content} /> : t('definitionUnavailable')}</h3>{personal && <LearningBadge state={personal.learning.state} />}</div>
            <div className="flex flex-wrap gap-2 mt-2 text-[11px] text-muted-foreground capitalize [&_span_+_span::before]:content-['·'] [&_span_+_span::before]:pr-2"><span>{label(sense.pos)}</span><span>{label(sense.tier)}</span>{sense.cefr_level && <span>CEFR {sense.cefr_level}</span>}{sense.register && <span>{label(sense.register)}</span>}</div>
            {sense.examples.length > 0 && <ul className="mt-3 text-muted-foreground text-[13px] leading-relaxed [&_li_+_li]:mt-1 [&_li::before]:content-['—'] [&_li::before]:mr-2">{sense.examples.map(example => <li key={example.id}><MarkedText text={example.content} /></li>)}</ul>}
            {sense.forms.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>{t('spellingAndForms')}</strong><div>{sense.forms.map(form => <span key={`${form.inf}:${form.surface}`}><b>{form.surface}</b> <small>{label(form.inf)}</small></span>)}</div></div>}
            {sense.patterns.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>{t('patterns')}</strong><PatternList patterns={sense.patterns} lemma={word.lemma} /></div>}
            {sense.collocations.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>{t('commonCombinations')}</strong><div>{sense.collocations.map(collocation => <span key={collocation}><MarkedText text={collocation} /></span>)}</div></div>}
            {sense.relations.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>{t('relatedMeanings')}</strong><div>{sense.relations.map(relation => <button key={`${relation.rel_type}:${relation.to_word_id}:${relation.to_sense_id}`} type="button" onClick={() => onSelectWord(relation.to_word_id, relation.to_word_lemma)}>{relation.to_word_lemma} <small>{label(relation.rel_type)}</small></button>)}</div></div>}
            {personal && <div className={`flex items-start gap-2 mt-3.5 text-muted-foreground text-[11px] leading-normal${personal.deck_count ? ' text-foreground' : ''}`}>
              <span className={`mt-[3px] size-2.5 shrink-0 rounded-full ${personal.deck_count ? 'bg-art-blue' : 'bg-border'}`} aria-hidden="true" />
              {personal.deck_count ? <div><strong>{t('inDeckCount', { count: personal.deck_count })}</strong>{account.profile && <MeaningSources nodeId={account.profile.library_node_id} sense={{ sense_id: personal.sense_id, sources: personal.decks, sources_has_more: personal.decks_has_more }} />}</div>
                : <span>{t('notInYourDecks')}</span>}
            </div>}
          </div><div className="[&_[data-slot=button]]:whitespace-nowrap max-[700px]:col-start-2">{account.status === 'ready' ? <Button variant="outline" onClick={() => onAdd(sense.id)}><Plus aria-hidden="true" />{t('addToDeck')}</Button>
            : <Button asChild variant="outline"><Link href={`/login?returnTo=${encodeURIComponent(`/app/dictionary?q=${word.lemma}`)}`}>{t('signInToAdd')}</Link></Button>}</div>
        </section>
      })}</div>
    </article>
    <aside className="border-l border-border min-w-0 [&_section]:p-5.5 [&_section]:border-b [&_section]:border-border [&_h3]:text-base [&_h3]:mb-4 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-relaxed max-[1000px]:border-l-0 max-[1000px]:border-t max-[1000px]:border-border max-[1000px]:grid max-[1000px]:grid-cols-2 max-[1000px]:[&_section]:border-r max-[1000px]:[&_section]:border-border max-[700px]:grid-cols-1 max-[700px]:[&_section]:px-0 max-[700px]:[&_section]:border-r-0" aria-label="Word context">
      {account.status === 'ready' && <section><h3>{t('yourProgress')}</h3>{contextError ? <p>{t('couldNotLoadLearningState')} <Button variant="link" onClick={retryContext}>{tCommon('retry')}</Button></p>
        : contexts ? <><div className="flex items-center gap-3.5 pb-4 [&_>_div]:flex [&_>_div]:flex-col [&_strong]:text-xl [&_strong]:tabular-nums [&_div_span]:text-muted-foreground [&_div_span]:text-[11px]"><span className="size-[54px] flex-none rounded-full relative after:content-[''] after:absolute after:inset-[7px] after:rounded-full after:bg-background" style={{ background: `conic-gradient(var(--art-blue) ${contexts.length ? studied / contexts.length * 100 : 0}%, var(--border) 0)` }} aria-hidden="true" /><div><strong>{studied} / {contexts.length}</strong><span>{t('sensesLearned')}</span></div></div><div className="grid grid-cols-3 gap-2.5 [&_>_div]:flex [&_>_div]:flex-col [&_>_div]:gap-1 [&_strong]:text-[23px] [&_strong]:tabular-nums [&_span]:text-[11px] [&_span]:text-muted-foreground"><div><strong>{contexts.filter(item => item.learning.state === 'new').length}</strong><span>{tHome('new')}</span></div><div><strong>{contexts.filter(item => item.learning.state === 'due').length}</strong><span>{tHome('dueNow')}</span></div><div><strong>{contexts.filter(item => item.learning.state === 'not_yet_due').length}</strong><span>{tHome('notDue')}</span></div></div></>
          : <p>{t('loadingLearningState')}</p>}</section>}
      {account.status === 'ready' && <section><h3>{t('inYourLibrary')}</h3>{contexts ? decks.length > 0 ? <><ul className="[&_li]:flex [&_li]:gap-2 [&_li]:items-center [&_li]:border-t [&_li]:border-border [&_li]:py-2.5 [&_li_>_svg]:size-5.5 [&_li_>_svg]:flex-none [&_a]:flex [&_a]:justify-between [&_a]:items-center [&_a]:gap-2.5 [&_a]:w-full [&_a]:text-xs [&_a]:text-left [&_a_span]:min-w-0 [&_a_span]:overflow-hidden [&_a_span]:text-ellipsis [&_a_span]:whitespace-nowrap [&_a_small]:ml-auto [&_a_small]:whitespace-nowrap [&_a_small]:text-muted-foreground [&_a_small]:text-[10px] [&_a_svg]:size-3.5 [&_a_svg]:flex-none">{decks.map(deck => <li key={deck.id}><Icon name="collection" /><Link href={nodeHref(deck)}><span>{deck.name}</span><small>{deckCountsPartial ? t('atLeast') : ''}{deck.count} {deck.count === 1 ? t('senseCount') : t('sensesCount')}</small></Link></li>)}</ul>{deckCountsPartial && <p>{t('someDecksHidden')}</p>}</> : <p>{t('notInDeck')}</p> : contextError ? <p>{t('decksUnavailable')}</p> : <p>{t('loadingDecks')}</p>}</section>}
      {account.status !== 'ready' && <section><h3>{t('inYourLibrary')}</h3><p>{t('signInToSeeLearningState')}</p></section>}
      {word.related.length > 0 && <section><h3>{t('relatedWords')}</h3><ul className="[&_li]:flex [&_li]:gap-2 [&_li]:items-center [&_li]:border-t [&_li]:border-border [&_li]:py-2.5 [&_button]:flex [&_button]:justify-between [&_button]:items-center [&_button]:gap-2.5 [&_button]:w-full [&_button]:text-xs [&_button]:text-left [&_button_svg]:size-3.5 [&_button_svg]:flex-none [&_small]:text-muted-foreground [&_small]:ml-auto">{word.related.map(related => <li key={related.to_word_id}><button type="button" onClick={() => onSelectWord(related.to_word_id, related.to_word_lemma)}>{related.to_word_lemma} <small>{label(related.rel_type)}</small></button></li>)}</ul></section>}
    </aside>
  </div>
}

export function DictionaryPage() {
  const hydrated = useHydrated()
  const queryClient = useQueryClient()
  const { services, scope } = useServices(), account = useAccount()
  const t = useTranslations('dictionary')
  const tCommon = useTranslations('common')
  const params = useSearchParams(), state = dictionaryState(params)
  const input = params.get('q') ?? '', deferred = useDeferredValue(input.trim()), selectedWordId = state.wordId
  const setInput = (value: string) => updateUrl({ q: value, word: null }, true)
  const setSelectedWordId = (id: number | null) => updateUrl({ word: id === null ? null : String(id) })
  const [reference, setReference] = useState<ReferenceHit | null>(null)
  useAssistantView(undefined, reference ? null : selectedWordId)
  const [jobId, setJobId] = useState<string | null>(null), [preparing, setPreparing] = useState(false), [prepareError, setPrepareError] = useState('')
  const [senseId, setSenseId] = useState<number | null>(null)
  const queries = dictionaryQueries(services, scope, deferred, selectedWordId)
  const search = useQuery(queries.search), detail = useQuery(queries.word)
  const context = useQuery({ ...queries.context, enabled: queries.context.enabled && account.status === 'ready' })
  const job = useQuery({ queryKey: [services.mode, scope, 'dictionary-generation', jobId], queryFn: ({ signal }) => services.dictionary.generation(jobId!, signal), enabled: Boolean(jobId),
    refetchInterval: query => ['running'].includes(query.state.data?.status ?? '') ? 1500 : false })
  useEffect(() => { if (job.data?.status === 'succeeded' && job.data.word_id) {
    void queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'dictionary-search'] }).then(() => {
      setSelectedWordId(job.data!.word_id); setReference(null); setJobId(null)
    })
  } }, [job.data, queryClient, scope, services.mode])
  async function prepare(hit: ReferenceHit) {
    setPreparing(true); setPrepareError('')
    try {
      const result = await services.dictionary.prepare(hit.reference_id, hit.display, new AbortController().signal)
      if (result.status === 'succeeded' && result.word_id) {
        setSelectedWordId(result.word_id); setReference(null)
      }
      else setJobId(result.task_id)
    } catch (cause) { setPrepareError(cause instanceof Error ? cause.message : 'Could not prepare this entry. Please retry.') }
    finally { setPreparing(false) }
  }
  async function saveSense(deckId: string) {
    if (senseId == null) return
    await services.library.updateDeckSenses(deckId, { add: [senseId], remove: [] }, new AbortController().signal)
    await invalidateLibrary(queryClient, services.mode, scope)
    toast.success(t('meaningAdded'))
    setSenseId(null)
  }
  async function createDeck(parentId: string, name: string, confirmPublication: boolean) {
    if (senseId == null) return
    await services.library.createDeck(parentId, name, [senseId], new AbortController().signal, confirmPublication)
    await invalidateLibrary(queryClient, services.mode, scope)
    toast.success(t('deckCreated'))
    setSenseId(null)
  }
  const showDetail = selectedWordId != null && !reference
  const results = search.data
  return <div className="w-full min-w-0 [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]"><div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">{t('title')}<span className="text-art-red" aria-hidden="true">.</span></h1></div><div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name="split-circle" /></div></header>
    <form className="flex items-center gap-3 border-b border-foreground min-h-[72px] [&_>_svg]:size-5 [&_>_svg]:flex-none [&_>_svg]:ml-3.5 [&_[data-slot=input]]:flex-1 [&_[data-slot=input]]:h-14 [&_[data-slot=input]]:p-0 [&_[data-slot=input]]:border-0 [&_[data-slot=input]]:text-[17px] [&_>_[data-slot=button]:last-child]:mr-2 max-[700px]:gap-1.5 max-[700px]:[&_>_svg]:ml-1 max-[700px]:[&_[data-slot=input]]:text-sm max-[700px]:[&_>_[data-slot=button]:last-child]:px-2.5 max-[700px]:[&_>_[data-slot=button]:last-child]:text-xs" role="search" onSubmit={event => { event.preventDefault(); setSelectedWordId(null); setReference(null) }}>
      <Search aria-hidden="true" /><Input type="text" inputMode="search" role="searchbox" disabled={!hydrated} aria-label={t('searchPlaceholder')} placeholder={t('searchPlaceholder')} value={input} maxLength={512} onChange={event => { setInput(event.target.value); setSelectedWordId(null); setReference(null); setJobId(null) }} />
      {input && <Button type="button" variant="ghost" size="icon" aria-label={tCommon('clearSearch')} onClick={() => { setInput(''); setSelectedWordId(null); setReference(null) }}><X aria-hidden="true" /></Button>}
      <Button type="submit">{t('searchButton')}</Button>
    </form>
    {!deferred && !showDetail ? <div className="flex items-center gap-5 min-h-[220px] border-b border-border text-muted-foreground [&_svg]:size-[68px] [&_svg]:ml-5"><Icon name="book" /><p>{t('searchPrompt')}</p></div>
      : deferred && <section className="border-b border-border pt-3.5 pb-4.5" aria-label="Search results"><div className="flex justify-between items-baseline gap-5 mb-2 [&_h2]:text-[15px] [&_span]:text-muted-foreground [&_span]:text-[13px]"><h2>{t('resultsFor', { query: deferred })}</h2>{search.isFetching && <span>{t('searching')}</span>}</div>
        {search.isError ? <HomeFailure label={t('dictionaryResults')} error={search.error} retry={() => { void search.refetch() }} />
          : search.isPending ? <HomeLoading label={t('dictionaryResults')} />
            : !results || results.items.length === 0 ? <p className="text-muted-foreground text-[13px]">{t('noEntries')}</p>
              : <div className="grid max-h-[260px] overflow-auto border-t border-border">{results.items.map(hit => hit.kind === 'word' ? (
                <button key={`word:${hit.word_id}`} type="button" className="grid grid-cols-[30px_minmax(0,1fr)] items-center gap-3 w-full min-h-12 px-3 py-2 text-left border-b border-border bg-transparent transition-colors duration-150 ease-out hover:bg-accent [&[aria-current=true]]:bg-accent focus-visible:relative focus-visible:z-[1] [&_>_.bauhaus-icon]:size-6 [&_strong]:text-sm [&_small]:block [&_small]:text-muted-foreground [&_small]:text-[11px] max-[700px]:grid-cols-[25px_minmax(0,1fr)] max-[700px]:gap-2" onClick={() => { setSelectedWordId(hit.word_id); setReference(null) }} aria-current={selectedWordId === hit.word_id && showDetail ? 'true' : undefined}>
                  <Icon name="book" /><span><strong>{hit.lemma}</strong>{hit.matched_surface !== hit.lemma && <small>Matched “{hit.matched_surface}”</small>}<span className="sr-only">{t('ready')}</span></span>
                </button>
              ) : (
                <button key={`reference:${hit.reference_id}`} type="button" className="grid grid-cols-[30px_minmax(0,1fr)_auto] items-center gap-3 w-full min-h-12 px-3 py-2 text-left border-b border-border bg-transparent transition-colors duration-150 ease-out hover:bg-accent [&[aria-current=true]]:bg-accent focus-visible:relative focus-visible:z-[1] [&_>_.bauhaus-icon]:size-6 [&_strong]:text-sm [&_small]:block [&_small]:text-muted-foreground [&_small]:text-[11px] max-[700px]:grid-cols-[25px_minmax(0,1fr)_auto] max-[700px]:gap-2" onClick={() => { setReference(hit); setSelectedWordId(null); setJobId(null); setPrepareError('') }} aria-current={reference?.reference_id === hit.reference_id ? 'true' : undefined}>
                  <Icon name="document" /><span><strong>{hit.display}</strong><span className="sr-only">{t('needsPreparation')}</span></span><span className="px-2 py-0.5 text-[11px] font-bold border border-art-blue/40 text-art-blue bg-art-blue/10 tracking-wider">{t('generate')}</span>
                </button>
              ))}</div>}
      </section>}
    {reference && <section className="border-b border-border bg-accent/25 p-6 md:p-8" aria-labelledby="reference-gen-heading">
      <div className="max-w-[760px]">
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-block px-2 py-0.5 text-[11px] font-bold uppercase tracking-widest bg-foreground text-background">{t('referenceTag')}</span>
          <span className="text-xs text-muted-foreground capitalize">{reference.entry_type.toLowerCase().replaceAll('_', ' ')}</span>
        </div>
        <h2 id="reference-gen-heading" className="text-3xl font-extrabold tracking-tight mb-2">{reference.display}</h2>
        <p className="text-sm text-muted-foreground leading-relaxed mb-6">{t('generateDesc')}</p>
        {jobId ? job.isError ? (
          <div className="border border-art-red bg-background p-4 text-sm" role="alert">
            <p className="font-semibold text-art-red mb-2">{t('couldNotCheckPreparation')}</p>
            <Button variant="outline" size="sm" onClick={() => { void job.refetch() }}>{t('checkAgain')}</Button>
          </div>
        ) : job.data?.status === 'failed' ? (
          <div className="border border-art-red bg-background p-4 text-sm" role="alert">
            <p className="font-semibold text-art-red mb-2">{t('preparationFailed')}{job.data.error ? `: ${job.data.error}` : '.'}</p>
            <Button variant="outline" size="sm" onClick={() => { void prepare(reference) }}>{tCommon('retry')}</Button>
          </div>
        ) : (
          <div className="border border-foreground bg-background p-5 text-sm" role="status">
            <div className="flex items-center gap-3 mb-3">
              <div className="size-4 border-2 border-art-blue border-t-transparent rounded-full animate-spin" aria-hidden="true" />
              <strong className="font-bold">{job.data?.stage ? t('generatingStage', { stage: job.data.stage }) : t('generatingWord')}</strong>
            </div>
            <div className="h-1.5 w-full bg-secondary overflow-hidden" aria-hidden="true"><div className="h-full bg-art-blue shimmer shimmer-bg w-3/4" /></div>
          </div>
        ) : account.status === 'ready' ? (
          <div className="flex items-center gap-3">
            <Button size="lg" onClick={() => { void prepare(reference) }} disabled={preparing}><Plus aria-hidden="true" />{preparing ? t('requesting') : t('prepareEntry')}</Button>
            <Button variant="ghost" onClick={() => setReference(null)}>{tCommon('cancel')}</Button>
          </div>
        ) : (
          <Button asChild size="lg"><Link href={`/login?returnTo=${encodeURIComponent(`/app/dictionary?q=${input.trim()}`)}`}>{t('signInToPrepare')}</Link></Button>
        )}
        {prepareError && <p className="mt-3 text-sm font-semibold text-art-red" role="alert">{prepareError}</p>}
      </div>
    </section>}
    {showDetail && (detail.isPending ? <HomeLoading label={t('word')} /> : detail.isError ? <HomeFailure label={t('word')} error={detail.error} retry={() => { void detail.refetch() }} />
      : <WordDetail key={detail.data.id} word={detail.data} contexts={context.data?.senses} contextError={context.isError ? context.error : null} retryContext={() => { void context.refetch() }} onAdd={setSenseId} onSelectWord={(id, lemma) => { setInput(lemma); setSelectedWordId(id) }} />)}
    {senseId != null && account.profile && <LibraryDestinationDialog open onOpenChange={open => { if (!open) setSenseId(null) }} profile={account.profile} kind="deck" action={t('addToDeck')}
      onConfirm={destination => saveSense(destination.id)} onCreateDeck={createDeck} />}
  </div>
}
