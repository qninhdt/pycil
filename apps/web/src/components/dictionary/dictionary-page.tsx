'use client'

import { useDeferredValue, useEffect, useState } from 'react'
import Link from 'next/link'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Plus, Search, X } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Motif, Icon } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { MarkedText } from '@/components/content/marked-text'
import { HomeFailure, HomeLoading } from '@/components/home/home-state'
import { LibraryDestinationDialog } from '@/components/library/library-destination-dialog'
import { MeaningSources } from '@/components/library/meaning-sources'
import { LearningBadge } from '@/components/library/library-shared'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { AvailableHit, DictionaryWord, SenseContext } from '@/lib/dictionary-model'
import { nodeHref } from '@/lib/library-model'
import { useServices } from '@/lib/services/provider'

const label = (value: string) => value.toLowerCase().replaceAll('_', ' ')

function WordDetail({ word, contexts, contextError, retryContext, onAdd, onSelectWord }: {
  word: DictionaryWord; contexts?: SenseContext[]; contextError?: Error | null; retryContext: () => void; onAdd: (id: number) => void; onSelectWord: (id: number, lemma: string) => void
}) {
  const account = useAccount()
  const groups = [...new Set(word.senses.map(sense => sense.pos))]
  const [active, setActive] = useState(groups[0] ?? '')
  const visible = groups.length > 1 ? word.senses.filter(sense => sense.pos === active) : word.senses
  const context = new Map(contexts?.map(sense => [sense.sense_id, sense]) ?? [])
  const decks = [...(contexts ?? []).reduce((items, sense) => {
    for (const deck of sense.decks) items.set(deck.id, { ...deck, count: (items.get(deck.id)?.count ?? 0) + 1 })
    return items
  }, new Map<string, SenseContext['decks'][number] & { count: number }>()).values()]
  const deckCountsPartial = contexts?.some(sense => sense.decks_has_more) ?? false
  const studied = contexts?.filter(sense => sense.learning.state !== 'NEW').length ?? 0
  const pronunciation = word.senses.find(sense => sense.ipa_uk || sense.ipa_us)
  return <div className="grid grid-cols-[minmax(0,7fr)_minmax(230px,3fr)] border-b border-border max-[1000px]:grid-cols-1">
    <article className="min-w-0 pr-6.5 pt-6.5 pb-8 max-[1000px]:pr-0"><header className="flex justify-between gap-4 items-start mb-4.5 [&_h2]:text-[clamp(36px,4vw,56px)] [&_h2]:leading-[1.1] [&_h2]:wrap-anywhere max-[700px]:[&_h2]:text-[38px]"><div>
      <h2>{word.lemma}</h2><div className="flex flex-wrap gap-3 mt-2 text-muted-foreground text-sm">{pronunciation?.ipa_uk && <span>UK {pronunciation.ipa_uk}</span>}{pronunciation?.ipa_us && <span>US {pronunciation.ipa_us}</span>}</div>
      {word.aliases.length > 0 && <p className="mt-1 text-muted-foreground text-xs">Also spelled {word.aliases.join(', ')}</p>}
    </div><span className="mt-2.5 capitalize text-[11px] tracking-widest">{label(word.type)} · {word.senses.length} {word.senses.length === 1 ? 'sense' : 'senses'}</span></header>
      {groups.length > 1 && <Tabs value={active} onValueChange={setActive} className="mb-3 [&_[data-slot=tabs-list]]:w-full [&_[data-slot=tabs-list]]:justify-start  [&_[data-slot=tabs-trigger]]:capitalize [&_[data-slot=tabs-trigger]_span]:ml-1.5 [&_[data-slot=tabs-trigger]_span]:text-muted-foreground [&_[data-slot=tabs-trigger]_span]:text-[11px]"><TabsList aria-label="Part of speech">{groups.map(pos => <TabsTrigger key={pos} value={pos}>{label(pos)} <span>{word.senses.filter(sense => sense.pos === pos).length}</span></TabsTrigger>)}</TabsList></Tabs>}
      <div className="dictionary-senses">{visible.map((sense, index) => {
        const personal = context.get(sense.id)
        return <section key={sense.id} id={`sense-${sense.id}`} className="grid grid-cols-[48px_minmax(0,1fr)_auto] gap-4 py-5 border-t border-border scroll-mt-7 max-[700px]:grid-cols-[36px_minmax(0,1fr)] max-[700px]:gap-2.5">
          <span className="text-[23px] font-bold tabular-nums text-muted-foreground">{String(index + 1).padStart(2, '0')}</span>
          <div className="dictionary-sense-body"><div className="flex items-start flex-wrap gap-2.5 [&_h3]:text-[17px] [&_h3]:leading-normal [&_h3]:max-w-[65ch] [&_[data-slot=badge]]:flex-none"><h3>{sense.definition ? <MarkedText text={sense.definition.content} /> : 'Definition unavailable'}</h3>{personal && <LearningBadge state={personal.learning.state} />}</div>
            <div className="flex flex-wrap gap-2 mt-2 text-[11px] text-muted-foreground capitalize [&_span_+_span::before]:content-['·'] [&_span_+_span::before]:pr-2"><span>{label(sense.pos)}</span><span>{label(sense.tier)}</span>{sense.cefr_level && <span>CEFR {sense.cefr_level}</span>}{sense.register && <span>{label(sense.register)}</span>}</div>
            {sense.examples.length > 0 && <ul className="mt-3 text-muted-foreground text-[13px] leading-relaxed [&_li_+_li]:mt-1 [&_li::before]:content-['—'] [&_li::before]:mr-2">{sense.examples.map(example => <li key={example.id}><MarkedText text={example.content} /></li>)}</ul>}
            {sense.usage_note && <p className="mt-3 text-xs leading-relaxed text-muted-foreground [&_strong]:text-foreground [&_strong]:mr-1.5"><strong>Usage</strong> {sense.usage_note}</p>}
            {sense.forms.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>Spelling & forms</strong><div>{sense.forms.map(form => <span key={`${form.inf}:${form.surface}`}><b>{form.surface}</b> <small>{label(form.inf)}</small></span>)}</div></div>}
            {sense.patterns.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>Patterns</strong><div>{sense.patterns.map(pattern => <span key={pattern}>{pattern}</span>)}</div></div>}
            {sense.collocations.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>Common combinations</strong><div>{sense.collocations.map(collocation => <span key={collocation}>{collocation}</span>)}</div></div>}
            {sense.relations.length > 0 && <div className="grid grid-cols-[116px_minmax(0,1fr)] gap-3 mt-3 text-[11px] leading-normal [&_>_strong]:text-muted-foreground [&_>_strong]:font-bold [&_>_div]:flex [&_>_div]:flex-wrap [&_>_div]:gap-x-3 [&_>_div]:gap-y-1 [&_span]:text-left [&_button]:text-left [&_small]:text-muted-foreground [&_small]:ml-1 [&_button]:text-art-blue [&_button]:underline [&_button]:underline-offset-2 max-[700px]:grid-cols-1 max-[700px]:gap-1"><strong>Related meanings</strong><div>{sense.relations.map(relation => <button key={`${relation.rel_type}:${relation.to_word_id}:${relation.to_sense_id}`} type="button" onClick={() => onSelectWord(relation.to_word_id, relation.to_word_lemma)}>{relation.to_word_lemma} <small>{label(relation.rel_type)}</small></button>)}</div></div>}
            {personal && <div className={`flex items-start gap-2 mt-3.5 text-muted-foreground text-[11px] leading-normal${personal.deck_count ? ' text-foreground' : ''}`}>
              <span className={`mt-[3px] size-2.5 shrink-0 rounded-full ${personal.deck_count ? 'bg-art-blue' : 'bg-border'}`} aria-hidden="true" />
              {personal.deck_count ? <div><strong>In {personal.deck_count} {personal.deck_count === 1 ? 'deck' : 'decks'}</strong>{account.profile && <MeaningSources nodeId={account.profile.library_node_id} sense={{ sense_id: personal.sense_id, sources: personal.decks, sources_has_more: personal.decks_has_more }} />}</div>
                : <span>Not in your decks</span>}
            </div>}
          </div><div className="[&_[data-slot=button]]:whitespace-nowrap  max-[700px]:col-start-2">{account.status === 'ready' ? <Button variant="outline" onClick={() => onAdd(sense.id)}><Plus aria-hidden="true" />Add to deck</Button>
            : <Button asChild variant="outline"><Link href={`/login?returnTo=${encodeURIComponent(`/app/dictionary?q=${word.lemma}`)}`}>Sign in to add</Link></Button>}</div>
        </section>
      })}</div>
    </article>
    <aside className="border-l border-border min-w-0 [&_section]:p-5.5 [&_section]:border-b [&_section]:border-border [&_h3]:text-base [&_h3]:mb-4 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-relaxed max-[1000px]:border-l-0 max-[1000px]:border-t max-[1000px]:border-border max-[1000px]:grid max-[1000px]:grid-cols-2 max-[1000px]:[&_section]:border-r max-[1000px]:[&_section]:border-border max-[700px]:grid-cols-1 max-[700px]:[&_section]:px-0 max-[700px]:[&_section]:border-r-0" aria-label="Word context">
      {account.status === 'ready' && <section><h3>Your progress</h3>{contextError ? <p>Could not load your learning state. <Button variant="link" onClick={retryContext}>Retry</Button></p>
        : contexts ? <><div className="flex items-center gap-3.5 pb-4 [&_>_div]:flex [&_>_div]:flex-col [&_strong]:text-xl [&_strong]:tabular-nums [&_div_span]:text-muted-foreground [&_div_span]:text-[11px]"><span className="size-[54px] flex-none rounded-full relative after:content-[''] after:absolute after:inset-[7px] after:rounded-full after:bg-background" style={{ background: `conic-gradient(var(--art-blue) ${contexts.length ? studied / contexts.length * 100 : 0}%, var(--border) 0)` }} aria-hidden="true" /><div><strong>{studied} / {contexts.length}</strong><span>senses learned</span></div></div><div className="grid grid-cols-3 gap-2.5 [&_>_div]:flex [&_>_div]:flex-col [&_>_div]:gap-1 [&_strong]:text-[23px] [&_strong]:tabular-nums [&_span]:text-[11px] [&_span]:text-muted-foreground"><div><strong>{contexts.filter(item => item.learning.state === 'NEW').length}</strong><span>New</span></div><div><strong>{contexts.filter(item => item.learning.state === 'DUE').length}</strong><span>Due</span></div><div><strong>{contexts.filter(item => item.learning.state === 'NOT_YET_DUE').length}</strong><span>Not yet due</span></div></div></>
          : <p>Loading your learning state…</p>}</section>}
      {account.status === 'ready' && <section><h3>In your Library</h3>{contexts ? decks.length > 0 ? <><ul className="[&_li]:flex [&_li]:gap-2 [&_li]:items-center [&_li]:border-t [&_li]:border-border [&_li]:py-2.5 [&_li_>_svg]:size-5.5 [&_li_>_svg]:flex-none [&_a]:flex [&_a]:justify-between [&_a]:items-center [&_a]:gap-2.5 [&_a]:w-full [&_a]:text-xs [&_a]:text-left [&_a_span]:min-w-0 [&_a_span]:overflow-hidden [&_a_span]:text-ellipsis [&_a_span]:whitespace-nowrap [&_a_small]:ml-auto [&_a_small]:whitespace-nowrap [&_a_small]:text-muted-foreground [&_a_small]:text-[10px] [&_a_svg]:size-3.5 [&_a_svg]:flex-none">{decks.map(deck => <li key={deck.id}><Icon name="collection" /><Link href={nodeHref(deck)}><span>{deck.name}</span><small>{deckCountsPartial ? 'at least ' : ''}{deck.count} {deck.count === 1 ? 'sense' : 'senses'}</small><ArrowRight aria-hidden="true" /></Link></li>)}</ul>{deckCountsPartial && <p>Some deck memberships are not shown here.</p>}</> : <p>Not in a deck yet.</p> : contextError ? <p>Decks unavailable.</p> : <p>Loading decks…</p>}</section>}
      {account.status !== 'ready' && <section><h3>Your Library</h3><p>Sign in to see learning state and saved decks.</p></section>}
      {word.related.length > 0 && <section><h3>Related words</h3><ul className="[&_li]:flex [&_li]:gap-2 [&_li]:items-center [&_li]:border-t [&_li]:border-border [&_li]:py-2.5 [&_button]:flex [&_button]:justify-between [&_button]:items-center [&_button]:gap-2.5 [&_button]:w-full [&_button]:text-xs [&_button]:text-left [&_button_svg]:size-3.5 [&_button_svg]:flex-none [&_small]:text-muted-foreground [&_small]:ml-auto">{word.related.map(related => <li key={related.to_word_id}><button type="button" onClick={() => onSelectWord(related.to_word_id, related.to_word_lemma)}>{related.to_word_lemma} <small>{label(related.rel_type)}</small></button></li>)}</ul></section>}
    </aside>
  </div>
}

export function DictionaryPage({ initialQuery = '' }: { initialQuery?: string }) {
  const queryClient = useQueryClient()
  const { services, scope } = useServices(), account = useAccount()
  const [input, setInput] = useState(initialQuery), deferred = useDeferredValue(input.trim())
  const [selectedWordId, setSelectedWordId] = useState<number | null>(null)
  const [available, setAvailable] = useState<AvailableHit | null>(null)
  const [jobId, setJobId] = useState<string | null>(null), [preparing, setPreparing] = useState(false), [prepareError, setPrepareError] = useState('')
  const [senseId, setSenseId] = useState<number | null>(null)
  const search = useQuery({ queryKey: [services.mode, scope, 'dictionary-search', deferred], queryFn: ({ signal }) => services.dictionary.search(deferred, signal), enabled: Boolean(deferred) })
  const detail = useQuery({ queryKey: [services.mode, scope, 'dictionary-word', selectedWordId], queryFn: ({ signal }) => services.dictionary.word(selectedWordId!, signal), enabled: selectedWordId != null })
  const context = useQuery({ queryKey: [services.mode, scope, 'dictionary-context', selectedWordId], queryFn: ({ signal }) => services.dictionary.context(selectedWordId!, signal), enabled: selectedWordId != null && account.status === 'ready' })
  const job = useQuery({ queryKey: [services.mode, scope, 'dictionary-generation', jobId], queryFn: ({ signal }) => services.dictionary.generation(jobId!, signal), enabled: Boolean(jobId),
    refetchInterval: query => ['QUEUED', 'RUNNING'].includes(query.state.data?.status ?? '') ? 1500 : false })
  useEffect(() => { if (job.data?.status === 'SUCCEEDED' && job.data.word_id) {
    if (job.data.stage === 'PARTIAL') toast.info('Entry ready. Some question types are unavailable; study uses the available questions.')
    void queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'dictionary-search'] }).then(() => {
      setSelectedWordId(job.data!.word_id); setAvailable(null); setJobId(null)
    })
  } }, [job.data, queryClient, scope, services.mode])
  async function prepare(hit: AvailableHit) {
    setPreparing(true); setPrepareError('')
    try {
      const result = await services.dictionary.prepare(hit.available_id, hit.display, new AbortController().signal)
      if (result.status === 'SUCCEEDED' && result.word_id) {
        if (result.stage === 'PARTIAL') toast.info('Entry ready. Some question types are unavailable; study uses the available questions.')
        setSelectedWordId(result.word_id); setAvailable(null)
      }
      else setJobId(result.generation_id)
    } catch (cause) { setPrepareError(cause instanceof Error ? cause.message : 'Could not prepare this entry. Please retry.') }
    finally { setPreparing(false) }
  }
  async function saveSense(deckId: string) {
    if (senseId == null) return
    await services.library.updateDeckSenses(deckId, { add: [senseId], remove: [] }, new AbortController().signal)
    await queryClient.invalidateQueries()
    toast.success('Meaning added to deck')
    setSenseId(null)
  }
  async function createDeck(parentId: string, name: string, confirmPublication: boolean) {
    if (senseId == null) return
    await services.library.createDeck(parentId, name, [senseId], new AbortController().signal, confirmPublication)
    await queryClient.invalidateQueries()
    toast.success('Deck created with this meaning')
    setSenseId(null)
  }
  const showDetail = selectedWordId != null && !available
  const results = search.data
  return <div className="w-full min-w-0 [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]"><div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">Dictionary<span className="text-art-red" aria-hidden="true">.</span></h1></div><div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name="split-circle" /></div></header>
    <form className="flex items-center gap-3 border-b border-foreground min-h-[72px] [&_>_svg]:size-5 [&_>_svg]:flex-none [&_>_svg]:ml-3.5 [&_[data-slot=input]]:flex-1 [&_[data-slot=input]]:h-14 [&_[data-slot=input]]:p-0 [&_[data-slot=input]]:border-0 [&_[data-slot=input]]:text-[17px] [&_>_[data-slot=button]:last-child]:mr-2 max-[700px]:gap-1.5 max-[700px]:[&_>_svg]:ml-1 max-[700px]:[&_[data-slot=input]]:text-sm max-[700px]:[&_>_[data-slot=button]:last-child]:px-2.5 max-[700px]:[&_>_[data-slot=button]:last-child]:text-xs" role="search" onSubmit={event => { event.preventDefault(); setSelectedWordId(null); setAvailable(null) }}>
      <Search aria-hidden="true" /><Input type="text" inputMode="search" role="searchbox" aria-label="Search word or expression" placeholder="Search word or expression" value={input} maxLength={512} onChange={event => { setInput(event.target.value); setSelectedWordId(null); setAvailable(null); setJobId(null) }} />
      {input && <Button type="button" variant="ghost" size="icon" aria-label="Clear search" onClick={() => { setInput(''); setSelectedWordId(null); setAvailable(null) }}><X aria-hidden="true" /></Button>}
      <Button type="submit">Search<ArrowRight aria-hidden="true" /></Button>
    </form>
    {!deferred && !showDetail ? <div className="flex items-center gap-5 min-h-[220px] border-b border-border text-muted-foreground [&_svg]:size-[68px] [&_svg]:ml-5"><Icon name="book" /><p>Search for a word or expression to explore its meanings.</p></div>
      : deferred && <section className="border-b border-border pt-3.5 pb-4.5" aria-label="Search results"><div className="flex justify-between items-baseline gap-5 mb-2 [&_h2]:text-[15px] [&_span]:text-muted-foreground [&_span]:text-[13px]"><h2>Results for “{deferred}”</h2>{search.isFetching && <span>Searching…</span>}</div>
        {search.isError ? <HomeFailure label="Dictionary results" error={search.error} retry={() => { void search.refetch() }} />
          : search.isPending ? <HomeLoading label="Dictionary results" />
            : !results || results.words.length + results.available.length === 0 ? <p className="text-muted-foreground text-[13px]">No entries found. Try another spelling or expression.</p>
              : <div className="grid max-h-[248px] overflow-auto border-t border-border">{results.words.map(hit => <button key={hit.word_id} type="button" className="grid grid-cols-[30px_minmax(0,1fr)_auto_18px] items-center gap-3 w-full min-h-12 px-3 py-2 text-left border-b border-border bg-transparent transition-colors duration-150 ease-out hover:bg-accent [&[aria-current=true]]:bg-accent focus-visible:relative focus-visible:z-[1] [&_>_.bauhaus-icon]:size-6 [&_strong]:text-sm [&_small]:block [&_small]:text-muted-foreground [&_small]:text-[11px] [&_>_svg:last-child]:size-4 max-[700px]:grid-cols-[25px_minmax(0,1fr)_auto_16px] max-[700px]:gap-2" onClick={() => { setSelectedWordId(hit.word_id); setAvailable(null) }} aria-current={selectedWordId === hit.word_id && showDetail ? 'true' : undefined}>
                <Icon name="book" /><span><strong>{hit.lemma}</strong>{hit.matched_surface !== hit.lemma && <small>Matched “{hit.matched_surface}”</small>}</span><small>Ready</small><ArrowRight aria-hidden="true" />
              </button>)}{results.available.map(hit => <button key={hit.available_id} type="button" className="grid grid-cols-[30px_minmax(0,1fr)_auto_18px] items-center gap-3 w-full min-h-12 px-3 py-2 text-left border-b border-border bg-transparent transition-colors duration-150 ease-out hover:bg-accent [&[aria-current=true]]:bg-accent focus-visible:relative focus-visible:z-[1] [&_>_.bauhaus-icon]:size-6 [&_strong]:text-sm [&_small]:block [&_small]:text-muted-foreground [&_small]:text-[11px] [&_>_svg:last-child]:size-4 max-[700px]:grid-cols-[25px_minmax(0,1fr)_auto_16px] max-[700px]:gap-2" onClick={() => { setAvailable(hit); setSelectedWordId(null); setJobId(null); setPrepareError('') }}>
                <Icon name="document" /><span><strong>{hit.display}</strong></span><small>Needs preparation</small><ArrowRight aria-hidden="true" />
              </button>)}</div>}
      </section>}
    {available && <section className="grid grid-cols-[60px_minmax(0,1fr)] gap-5 px-5 py-8 border-b border-border [&_>_svg]:size-[52px] [&_h2]:text-3xl [&_p]:my-2.5 [&_p]:mb-4.5 [&_p]:text-sm [&_p]:text-muted-foreground"><Icon name="document" /><div><h2>{available.display}</h2><p>This entry needs preparation before its meanings can be read or added to a deck.</p>
      {jobId ? job.isError ? <p role="alert">Could not check preparation status. <Button variant="link" onClick={() => { void job.refetch() }}>Check again</Button></p>
        : job.data?.status === 'FAILED' ? <><p role="alert">Preparation failed{job.data.error ? `: ${job.data.error}` : '.'}</p><Button onClick={() => { void prepare(available) }}>Retry preparation</Button></>
          : <p role="status">{job.data?.status === 'RUNNING' ? job.data.stage || 'Preparing entry…' : 'Waiting to prepare…'}</p>
        : account.status === 'ready' ? <Button onClick={() => { void prepare(available) }} disabled={preparing}>{preparing ? 'Requesting…' : 'Prepare entry'}</Button>
          : <Button asChild><Link href={`/login?returnTo=${encodeURIComponent(`/app/dictionary?q=${input.trim()}`)}`}>Sign in to prepare</Link></Button>}
      {prepareError && <p role="alert">{prepareError}</p>}</div></section>}
    {showDetail && (detail.isPending ? <HomeLoading label="word" /> : detail.isError ? <HomeFailure label="word" error={detail.error} retry={() => { void detail.refetch() }} />
      : <WordDetail key={detail.data.id} word={detail.data} contexts={context.data?.senses} contextError={context.isError ? context.error : null} retryContext={() => { void context.refetch() }} onAdd={setSenseId} onSelectWord={(id, lemma) => { setInput(lemma); setSelectedWordId(id) }} />)}
    {senseId != null && account.profile && <LibraryDestinationDialog open onOpenChange={open => { if (!open) setSenseId(null) }} profile={account.profile} kind="DECK" action="Add to deck"
      onConfirm={destination => saveSense(destination.id)} onCreateDeck={createDeck} />}
  </div>
}
