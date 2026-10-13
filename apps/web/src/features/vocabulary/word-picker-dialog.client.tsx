'use client'

import { useDeferredValue, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, X } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { MarkedText } from '@/components/content/marked-text'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import type { DictionarySense, WordPreview } from '@/lib/api/vocabulary'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useServices } from '@/lib/api/services/provider.client'
import { useTranslations } from 'next-intl'

type Selection = { word: string; sense: DictionarySense }
type Props = { open: boolean; onOpenChange: (open: boolean) => void; deckId: string }

export function WordPickerDialog({ open, onOpenChange, deckId }: Props) {
  const { services, scope } = useServices(), queryClient = useQueryClient()
  const t = useTranslations('library')
  const tDict = useTranslations('dictionary')
  const tCommon = useTranslations('common')
  const [input, setInput] = useState(''), q = useDeferredValue(input.trim())
  const [pos, setPos] = useState('all'), [selected, setSelected] = useState<Map<number, Selection>>(() => new Map())
  const [saving, setSaving] = useState(false), [error, setError] = useState('')
  const [jobId, setJobId] = useState<string | null>(null), [pendingEntry, setPendingEntry] = useState<string | null>(null)
  const search = useQuery({ queryKey: [services.mode, scope, 'dictionary-search', q], queryFn: ({ signal }) => services.dictionary.search(q, signal), enabled: open && Boolean(q) })
  const ids = search.data?.items.flatMap(hit => hit.kind === 'word' ? [hit.word_id] : []) ?? []
  const previews = useQuery({ queryKey: [services.mode, scope, 'word-previews', ids], queryFn: ({ signal }) => services.dictionary.previews(ids, signal), enabled: open && ids.length > 0 })
  const job = useQuery({ queryKey: [services.mode, scope, 'picker-generation', jobId], queryFn: ({ signal }) => services.dictionary.generation(jobId!, signal), enabled: open && Boolean(jobId),
    refetchInterval: query => ['running'].includes(query.state.data?.status ?? '') ? 1500 : false })
  useEffect(() => { if (job.data?.status === 'succeeded') {
    void queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'dictionary-search'] }).then(() => {
      setJobId(null); setPendingEntry(null)
    })
  } }, [job.data, queryClient, scope, services.mode])
  const availablePos = [...new Set(previews.data?.flatMap(word => word.senses.map(sense => sense.pos)) ?? [])]
  function toggle(word: WordPreview, sense: DictionarySense) {
    setSelected(previous => { const next = new Map(previous); if (next.has(sense.id)) next.delete(sense.id); else next.set(sense.id, { word: word.lemma, sense }); return next })
  }
  function toggleWord(word: WordPreview) {
    const senses = word.senses.filter(sense => pos === 'all' || sense.pos === pos)
    setSelected(previous => { const next = new Map(previous); const all = senses.every(sense => next.has(sense.id)); for (const sense of senses) {
      if (all) next.delete(sense.id); else next.set(sense.id, { word: word.lemma, sense })
    } return next })
  }
  async function save() {
    if (!selected.size) return
    setSaving(true); setError('')
    try {
      await services.library.updateDeckSenses(deckId, { add: [...selected.keys()], remove: [] }, new AbortController().signal)
      await invalidateLibrary(queryClient, services.mode, scope)
      setSelected(new Map()); onOpenChange(false); toast.success(t('meaningsAddedToDeck'))
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotAddMeanings')) }
    finally { setSaving(false) }
  }
  async function prepare(referenceId: string, display: string) {
    setError(''); setPendingEntry(display)
    try {
      const result = await services.dictionary.prepare(referenceId, display, new AbortController().signal)
      if (result.status === 'succeeded') { await queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'dictionary-search'] }); setPendingEntry(null) }
      else setJobId(result.task_id)
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotPrepareEntry')); setPendingEntry(null) }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="w-[min(1360px,calc(100vw-32px))] max-w-none sm:max-w-none h-[min(90vh,900px)] max-h-none flex flex-col gap-0 p-0 bg-background [&_[data-slot=dialog-header]]:text-left [&_[data-slot=dialog-header]]:px-7 [&_[data-slot=dialog-header]]:pt-5 [&_[data-slot=dialog-header]]:pb-4.5 [&_[data-slot=dialog-header]]:border-b [&_[data-slot=dialog-header]]:border-border [&_[data-slot=dialog-title]]:text-[27px] [&_[data-slot=dialog-title]]:font-extrabold [&_[data-slot=dialog-title]]:tracking-tight [&_[data-slot=dialog-description]]:text-[13px] max-[700px]:w-[calc(100vw-16px)] max-[700px]:h-[calc(100dvh-16px)]">
    <DialogHeader><DialogTitle>{t('addWordsToDeck')}</DialogTitle><DialogDescription>{t('addWordsDescription')}</DialogDescription></DialogHeader>
    <div className="grid grid-cols-[minmax(0,7fr)_minmax(270px,3fr)] flex-1 min-h-0 max-[1000px]:grid-cols-[minmax(0,6fr)_minmax(240px,4fr)] max-[700px]:grid-cols-1 max-[700px]:overflow-auto"><div className="flex flex-col min-w-0 min-h-0 pt-5 pr-5.5 pl-7 max-[700px]:min-h-[360px] max-[700px]:px-4 max-[700px]:pt-3.5">
      <div className="mb-3.5 flex gap-3 max-[700px]:flex-wrap"><div className="flex items-center gap-2 border border-border [&_>_svg]:size-[17px] [&_>_svg]:flex-none [&_[data-slot=input]]:border-0 flex-1 min-w-0 px-2.5"><Search aria-hidden="true" /><Input type="text" inputMode="search" role="searchbox" aria-label={t('searchWords')} placeholder={t('searchWordsPlaceholder')} value={input} maxLength={512} onChange={event => setInput(event.target.value)} />
        {input && <Button variant="ghost" size="icon-sm" aria-label={tCommon('clearSearch')} onClick={() => setInput('')}><X aria-hidden="true" /></Button>}</div>
        <NativeSelect className="min-w-[165px] max-[700px]:w-full" aria-label={t('partOfSpeech')} value={pos} onChange={event => setPos(event.target.value)}><option value="all">{t('allPartsOfSpeech')}</option>{availablePos.map(value => <option key={value} value={value}>{value.toLowerCase()}</option>)}</NativeSelect></div>
      <div className="overflow-auto min-h-0 pr-1.5" aria-live="polite">{!q ? <p className="py-6 text-muted-foreground text-[13px]">{t('searchToBrowse')}</p>
        : search.isError ? <div className="py-6 text-muted-foreground text-[13px]"><p>{t('couldNotSearchWords')}</p><Button variant="link" onClick={() => { void search.refetch() }}>{tCommon('retry')}</Button></div>
          : search.isPending ? <p className="py-6 text-muted-foreground text-[13px]">{tCommon('loading')}</p>
            : previews.isError ? <div className="py-6 text-muted-foreground text-[13px]"><p>{t('couldNotLoadMeanings')}</p><Button variant="link" onClick={() => { void previews.refetch() }}>{tCommon('retry')}</Button></div>
              : previews.isPending && ids.length > 0 ? <p className="py-6 text-muted-foreground text-[13px]">{tCommon('loading')}</p>
                : <>{search.data?.items.map(hit => {
                  if (hit.kind === 'reference') return (
                    <div className="flex items-center justify-between gap-3 py-3 border-t border-border" key={`reference:${hit.reference_id}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="[&_>_.bauhaus-icon]:size-6 flex-none"><Icon name="document" /></span>
                        <div className="min-w-0">
                          <strong className="block text-sm truncate">{hit.display}</strong>
                          <small className="block text-muted-foreground text-[11px] capitalize">{hit.entry_type.toLowerCase().replaceAll('_', ' ')}</small>
                        </div>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => { void prepare(hit.reference_id, hit.display) }} disabled={pendingEntry === hit.display && job.data?.status !== 'failed'}>
                        {pendingEntry === hit.display ? tDict('requesting') : tDict('generate')}
                      </Button>
                    </div>
                  )
                  const word = previews.data?.find(word => word.word_id === hit.word_id)
                  if (!word || !word.senses.some(sense => pos === 'all' || sense.pos === pos)) return null
                  const senses = word.senses.filter(sense => pos === 'all' || sense.pos === pos)
                  return <section className="grid grid-cols-[minmax(150px,30%)_minmax(0,1fr)] gap-5 py-4 border-t border-border max-[1000px]:grid-cols-1 max-[1000px]:gap-2.5" key={word.word_id}><div className="flex gap-2.5 items-start min-w-0 [&_>_svg]:size-10 [&_>_svg]:flex-none [&_h3]:text-[22px] [&_h3]:font-extrabold [&_h3]:tracking-tight [&_h3]:wrap-anywhere [&_span]:text-muted-foreground [&_span]:text-[11px]"><Icon name="book" /><div><h3>{word.lemma}</h3><span>{word.entry_type.toLowerCase().replaceAll('_', ' ')}</span></div></div>
                    <div className="border-l border-border pl-4.5 max-[1000px]:border-l-0 max-[1000px]:pl-0"><button className="block mr-0 mb-2 ml-auto text-muted-foreground text-[11px] underline" onClick={() => toggleWord(word)}>{t('selectAction', { mode: senses.every(sense => selected.has(sense.id)) ? t('selectNone') : t('selectAll'), count: senses.length })}</button>
                      {senses.map(sense => <label key={sense.id} className="flex gap-3 py-2.5 border-t border-border cursor-pointer [&_input]:size-4 [&_input]:mt-0.5 [&_input]:accent-art-blue [&_input]:flex-none [&_>_span]:min-w-0 [&_strong]:block [&_small]:block [&_em]:block [&_strong]:text-[13px] [&_strong]:leading-normal [&_small]:text-muted-foreground [&_small]:text-[10px] [&_small]:capitalize [&_small]:mt-0.5 [&_em]:text-muted-foreground [&_em]:text-xs [&_em]:not-italic [&_em]:mt-0.5 [&_em]:leading-normal"><input type="checkbox" checked={selected.has(sense.id)} onChange={() => toggle(word, sense)} /><span><strong>{sense.definition ? <MarkedText text={sense.definition.content} /> : t('definitionUnavailable')}</strong><small>{sense.pos.toLowerCase()} · {sense.tier.toLowerCase().replaceAll('_', ' ')}{sense.cefr_level ? ` · ${sense.cefr_level}` : ''}</small>{sense.examples[0] && <em><MarkedText text={sense.examples[0].content} /></em>}</span></label>)}</div>
                  </section>
                })}
                {search.data?.items.length === 0 && <p className="py-6 text-muted-foreground text-[13px]">{t('noEntriesFound')}</p>}</>}
        {jobId && <p className="py-3 text-muted-foreground text-xs" role="status">{job.isError ? <>{t('couldNotCheckPreparation')} <Button variant="link" onClick={() => { void job.refetch() }}>{t('checkAgain')}</Button></>
          : job.data?.status === 'failed' ? <>{t('preparationFailed')} <Button variant="link" onClick={() => { setJobId(null); setPendingEntry(null) }}>{tCommon('retry')}</Button></>
            : t('preparingEntry', { entry: pendingEntry ?? 'entry' })}</p>}
      </div>
    </div><aside className="min-w-0 min-h-0 flex flex-col border-l border-border pt-5 px-5.5 max-[700px]:min-h-[210px] max-[700px]:border-l-0 max-[700px]:border-t max-[700px]:border-border max-[700px]:px-4 max-[700px]:pt-3.5" aria-label={t('selectedMeanings')}><div className="flex justify-between items-center gap-2 pb-3.5 [&_h3]:text-base [&_h3]:font-extrabold [&_h3_span]:inline-block [&_h3_span]:ml-1.5 [&_h3_span]:px-1.5 [&_h3_span]:py-0.5 [&_h3_span]:bg-accent [&_h3_span]:text-[11px]"><h3>{t('selectedMeanings')} <span>{selected.size}</span></h3><Button variant="link" disabled={!selected.size} onClick={() => setSelected(new Map())}>{t('clearAll')}</Button></div>
      <div className="flex-1 min-h-0 overflow-auto border-t border-border [&_>_p]:pt-5.5 [&_>_p]:text-muted-foreground [&_>_p]:text-xs max-[700px]:max-h-[170px]">{selected.size ? [...selected.values()].map(({ word, sense }) => <div key={sense.id} className="grid grid-cols-[28px_minmax(0,1fr)_22px] gap-2.5 items-start py-3.5 border-b border-border [&_>_svg]:size-[26px] [&_strong]:text-[13px] [&_strong_small]:text-[10px] [&_strong_small]:font-normal [&_strong_small]:text-muted-foreground [&_p]:text-xs [&_p]:leading-normal [&_p]:text-muted-foreground [&_button_svg]:size-4"><Icon name="book" /><div><strong>{word} <small>{sense.pos.toLowerCase()}</small></strong><p>{sense.definition ? <MarkedText text={sense.definition.content} /> : t('definitionUnavailable')}</p></div>
        <button aria-label={t('removeMeaningAria', { word, definition: sense.definition?.content ?? 'meaning' })} onClick={() => setSelected(previous => { const next = new Map(previous); next.delete(sense.id); return next })}><X aria-hidden="true" /></button></div>)
        : <p>{t('noMeaningsSelected')}</p>}</div>
      {error && <p className="text-destructive text-xs px-6 py-2" role="alert">{error}</p>}
      <div className="flex justify-between items-center gap-3 py-4 border-t border-border text-xs font-bold "><span>{t('meaningsSelectedCount', { count: selected.size })}</span><Button onClick={() => { void save() }} disabled={!selected.size || saving}>{saving ? t('adding') : t('addToDeck')}</Button></div>
    </aside></div>
  </DialogContent></Dialog>
}
