'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, ArrowRight, X } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { Flashcard } from './flashcard'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'
import { libraryHref, publishedHref, type Meaning } from '@/lib/library-model'

export function FlashcardFocus() {
  const account = useAccount(), { services } = useServices(), params = useSearchParams()
  const profile = account.profile, profileId = profile?.id, nodeId = params.get('node') || profile?.library_node_id || ''
  const backHref = params.get('owner') && nodeId ? publishedHref(params.get('owner')!, nodeId) : libraryHref(nodeId)
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
        const page = await services.library.meanings(nodeId, { cursor, limit: 100, state: 'ALL', sort: 'LEMMA_ASC' }, controller.signal)
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
  if (account.status !== 'ready' || !profile) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Flashcards</h1><p>{account.status === 'loading' ? 'Loading…' : 'Sign in to open flashcards.'}</p><Button asChild><Link href="/login">Sign in</Link></Button></main>
  return <main className="min-h-svh bg-background text-foreground"><header className="h-[78px] grid grid-cols-[78px_minmax(120px,1fr)_minmax(190px,420px)_minmax(120px,1fr)] items-center border-b border-foreground [&_>_a]:grid [&_>_a]:place-items-center [&_>_a]:h-full [&_>_a]:border-r [&_>_a]:border-foreground [&_>_a:hover]:bg-accent [&_>_a_svg]:size-6 max-[760px]:h-16 max-[760px]:grid-cols-[56px_minmax(0,1fr)_120px]"><Link href={backHref} aria-label="Exit flashcards"><X aria-hidden="true" /></Link>
    <div className="flex gap-3 items-baseline min-w-0 px-6 whitespace-nowrap overflow-hidden text-ellipsis [&_strong]:font-extrabold [&_span]:text-muted-foreground max-[760px]:px-3 max-[760px]:gap-2 max-[760px]:text-[13px] max-[760px]:[&_strong]:overflow-hidden max-[760px]:[&_strong]:text-ellipsis"><strong>{name}</strong><span>Flashcards</span></div>
    <div className="flex items-center gap-4 min-w-0 [&_small]:flex-none [&_small]:text-xs [&_small]:text-muted-foreground [&_small]:tabular-nums max-[760px]:pr-3 max-[760px]:gap-1.5 max-[760px]:overflow-hidden"><div className="w-full h-2 bg-muted overflow-hidden [&_span]:block [&_span]:h-full [&_span]:bg-foreground [&_span]:transition-[width] [&_span]:duration-200 [&_span]:ease-out max-[760px]:min-w-[18px] motion-reduce:[&_span]:transition-none"><span style={{ width: `${senses.length ? (index + 1) / senses.length * 100 : 0}%` }} /></div><small>{senses.length ? `${index + 1} / ${senses.length}` : '0 cards'}</small></div>
  </header>
    {loading || loadedKey !== key ? <section className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Preparing flashcards…</h1></section> : error ? <section className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Could not load flashcards.</h1><p role="alert">{error}</p><Button asChild><Link href={backHref}>Back to Library</Link></Button></section>
      : !sense ? <section className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>No flashcards here yet.</h1><p>Add meanings to this deck or choose another folder.</p><Button asChild><Link href={backHref}>Back to Library</Link></Button></section>
        : <div className="w-[min(calc(100%-40px),1340px)] min-h-[calc(100svh-78px)] grid grid-cols-[56px_minmax(0,1fr)_56px] content-center items-center gap-7 m-auto py-9 [&_>_[data-slot=button]]:size-14 [&_>_[data-slot=button]]:rounded-full [&_>_article]:min-h-[min(580px,65svh)] [&_>_p]:col-span-full [&_>_p]:text-center [&_>_p]:text-muted-foreground [&_>_p]:text-[11px] max-[760px]:w-[calc(100%-24px)] max-[760px]:grid-cols-[44px_minmax(0,1fr)_44px] max-[760px]:gap-2 max-[760px]:[&_>_[data-slot=button]]:size-11 max-[760px]:[&_>_article]:col-span-full max-[760px]:[&_>_article]:row-start-1 max-[760px]:[&_>_[data-slot=button]:first-child]:col-start-1 max-[760px]:[&_>_[data-slot=button]:first-child]:row-start-2 max-[760px]:[&_>_[data-slot=button]:nth-child(3)]:col-start-3 max-[760px]:[&_>_[data-slot=button]:nth-child(3)]:row-start-2"><Button variant="outline" size="icon" aria-label="Previous flashcard" onClick={() => move(-1)} disabled={index === 0}><ArrowLeft aria-hidden="true" /></Button>
          <Flashcard cardId={sense.sense_id} content={sense} ordinal={index + 1} revealed={revealed} onRevealedChange={setRevealed} />
          <Button variant="outline" size="icon" aria-label="Next flashcard" onClick={() => move(1)} disabled={index === senses.length - 1}><ArrowRight aria-hidden="true" /></Button>
          <p>Space to reveal · ← → to navigate · Browsing flashcards does not change your review schedule.</p>
        </div>}
  </main>
}
