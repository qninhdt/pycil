'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, ArrowRight, X } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { Flashcard } from './flashcard'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'
import { libraryHref, publishedHref, type Meaning } from '@/lib/library-model'

export function FlashcardFocus() {
  const account = useAccount(), { services } = useServices(), params = useSearchParams()
  const profile = account.profile, profileId = profile?.id, nodeId = params?.get('node') || profile?.library_node_id || ''
  const backHref = params?.get('owner') && nodeId ? publishedHref(params.get('owner')!, nodeId) : libraryHref(nodeId)
  const key = profile ? `pycil:flashcards:${profile.id}:${nodeId}` : ''
  const [senses, setSenses] = useState<Meaning[]>([]), [name, setName] = useState('Flashcards')
  const [index, setIndex] = useState(0), [revealed, setRevealed] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState('')
  const [loadedKey, setLoadedKey] = useState('')
  useEffect(() => {
    if (!profileId || !nodeId) return
    const controller = new AbortController()
    setLoading(true); setError('')
    async function load() {
      const detail = await services.library.details(nodeId, controller.signal)
      if (detail.reference_available === false) throw new Error('The source is no longer available.')
      const pages: Meaning[] = []
      let cursor: string | undefined
      do {
        const page = await services.library.meanings(nodeId, { cursor, limit: 100, state: 'all', sort: 'lemma_asc' }, controller.signal)
        pages.push(...page.senses); cursor = page.next_cursor ?? undefined
      } while (cursor)
      if (controller.signal.aborted) return
      setName(detail.name); setSenses(pages)
      try {
        const saved = JSON.parse(localStorage.getItem(key) || '{}') as { index?: number; revealed?: boolean }
        setIndex(Math.min(Math.max(0, saved.index ?? 0), Math.max(0, pages.length - 1))); setRevealed(Boolean(saved.revealed))
      } catch { setIndex(0); setRevealed(false) }
      setLoadedKey(key); setLoading(false)
    }
    void load().catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Could not load flashcards.'); setLoadedKey(key); setLoading(false) } })
    return () => controller.abort()
  }, [profileId, nodeId, key, services.library])
  useEffect(() => {
    if (!key || loading || loadedKey !== key) return
    try { localStorage.setItem(key, JSON.stringify({ index, revealed })) } catch { /* Browsing still works without persistence. */ }
  }, [key, index, revealed, loading, loadedKey])
  const move = useCallback((delta: number) => { if (!senses.length) return; setIndex(value => Math.max(0, Math.min(senses.length - 1, value + delta))); setRevealed(false) }, [senses.length])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
      if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
      if (event.code === 'Space' && !(event.target instanceof HTMLButtonElement)) { event.preventDefault(); setRevealed(value => !value) }
    }
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey)
  }, [move])
  const sense = senses[index]
  const tLearning = useTranslations('learning')
  const tNav = useTranslations('nav')
  if (account.status !== 'ready' || !profile) return <main className="h-svh max-h-svh overflow-hidden flex flex-col items-center justify-center p-8 bg-background text-foreground"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>{tLearning('flashcards')}</h1><p>{account.status === 'loading' ? tNav('loadingAccount') : tNav('signInToLearn')}</p><Button asChild><Link href="/login">{tNav('signIn')}</Link></Button></div></main>
  return <main className="h-svh max-h-svh overflow-hidden flex flex-col bg-background text-foreground"><header className="flex-none h-[78px] grid grid-cols-[78px_minmax(120px,1fr)_minmax(190px,420px)_minmax(120px,1fr)] items-center border-b border-foreground [&_>_a]:grid [&_>_a]:place-items-center [&_>_a]:h-full [&_>_a]:border-r [&_>_a]:border-foreground [&_>_a:hover]:bg-accent [&_>_a_svg]:size-6 max-[760px]:h-16 max-[760px]:grid-cols-[56px_minmax(0,1fr)_120px]"><Link href={backHref} aria-label={tLearning('exitFlashcards')}><X aria-hidden="true" /></Link>
    <div className="flex gap-3 items-baseline min-w-0 px-6 whitespace-nowrap overflow-hidden text-ellipsis [&_strong]:font-extrabold [&_span]:text-muted-foreground max-[760px]:px-3 max-[760px]:gap-2 max-[760px]:text-[13px] max-[760px]:[&_strong]:overflow-hidden max-[760px]:[&_strong]:text-ellipsis"><strong>{name}</strong><span>{tLearning('flashcards')}</span></div>
    <div className="flex items-center gap-4 min-w-0 [&_small]:flex-none [&_small]:text-xs [&_small]:text-muted-foreground [&_small]:tabular-nums max-[760px]:pr-3 max-[760px]:gap-1.5 max-[760px]:overflow-hidden"><div className="w-full h-2 bg-muted overflow-hidden [&_span]:block [&_span]:h-full [&_span]:bg-foreground [&_span]:transition-[width] [&_span]:duration-200 [&_span]:ease-out max-[760px]:min-w-[18px] motion-reduce:[&_span]:transition-none"><span style={{ width: `${senses.length ? (index + 1) / senses.length * 100 : 0}%` }} /></div><small>{senses.length ? `${index + 1} / ${senses.length}` : tLearning('zeroCards')}</small></div>
  </header>
    {loading || loadedKey !== key ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1 className="shimmer text-foreground/70">{tLearning('preparingFlashcards')}</h1></div></section> : error ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>{tLearning('couldNotLoad')}</h1><p role="alert">{error}</p><Button asChild><Link href={backHref}>{tLearning('backToLibrary')}</Link></Button></div></section>
      : !sense ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>{tLearning('noFlashcardsYet')}</h1><p>{tLearning('addMeaningsPrompt')}</p><Button asChild><Link href={backHref}>{tLearning('backToLibrary')}</Link></Button></div></section>
        : <div className="flex-1 min-h-0 flex flex-col items-center justify-center p-3 sm:p-5 md:p-6 overflow-hidden">
            <div className="w-[min(calc(100%-32px),1240px)] flex-1 min-h-0 grid grid-cols-[56px_minmax(0,1fr)_56px] content-center items-center gap-4 sm:gap-7 my-auto max-[760px]:w-full max-[760px]:grid-cols-[44px_minmax(0,1fr)_44px] max-[760px]:gap-2">
              <Button variant="outline" size="icon" className="size-14 rounded-none max-[760px]:size-11 border-foreground max-[760px]:col-start-1 max-[760px]:row-start-2" aria-label={tLearning('previousCard')} onClick={() => move(-1)} disabled={index === 0}><ArrowLeft aria-hidden="true" /></Button>
              <div className="h-[min(540px,calc(100svh-190px))] max-h-[560px] min-h-[300px] w-full max-[760px]:col-span-full max-[760px]:row-start-1"><Flashcard cardId={sense.sense_id} content={sense} ordinal={index + 1} revealed={revealed} onRevealedChange={setRevealed} /></div>
              <Button variant="outline" size="icon" className="size-14 rounded-none max-[760px]:size-11 border-foreground max-[760px]:col-start-3 max-[760px]:row-start-2" aria-label={tLearning('nextCard')} onClick={() => move(1)} disabled={index === senses.length - 1}><ArrowRight aria-hidden="true" /></Button>
            </div>
            <p className="flex-none text-center text-muted-foreground text-[11px] mt-2 max-[760px]:mt-1">{tLearning('flashcardShortcuts')}</p>
          </div>}
  </main>
}
