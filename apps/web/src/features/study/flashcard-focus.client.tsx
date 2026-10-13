'use client'

import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { flashcardQuery } from '@/features/study/flashcard-query'
import { nodeQuery, progressQuery } from '@/features/library/queries'
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, ArrowRight, X } from '@/components/artwork/artwork'
import { useAccount } from '@/features/account/account.client'
import { Flashcard } from './flashcard.client'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/api/services/provider.client'
import { libraryHref, publishedHref, publicCollectionHref } from '@/features/library/model'

export function FlashcardFocus() {
  const account = useAccount(), { services, scope } = useServices(), params = useSearchParams()
  const profile = account.profile, nodeId = params?.get('node') || profile?.library_node_id || ''
  const backHref = params?.get('owner') && nodeId ? params.get('owner') === profile?.id ? publishedHref(nodeId) : publicCollectionHref(params.get('owner')!, nodeId) : libraryHref(nodeId)
  const key = profile ? `pycil:flashcards:${profile.id}:${nodeId}` : ''
  const node = useQuery(nodeQuery(services, scope, nodeId))
  const progress = useQuery(progressQuery(services, scope, nodeId))
  const cards = useInfiniteQuery({ ...flashcardQuery(services, scope, nodeId), enabled: Boolean(nodeId) && account.status === 'ready' && node.data?.reference_available !== false })
  const senses = cards.data?.pages.flatMap(page => page.senses) ?? [], name = node.data?.name ?? 'Flashcards'
  const [index, setIndex] = useState(0), [revealed, setRevealed] = useState(false), [loadedKey, setLoadedKey] = useState('')
  const total = progress.data?.total ?? 0
  const resolvedNodeId = node.data?.id
  const loading = !node.isError && node.data?.reference_available !== false && (node.isPending || progress.isPending || cards.isPending || index >= senses.length && cards.hasNextPage)
  const error = node.error?.message || progress.error?.message || cards.error?.message || (node.data?.reference_available === false ? 'The source is no longer available.' : '')
  useEffect(() => {
    if (!key || !resolvedNodeId || !progress.data || loadedKey === key) return
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(key) || '{}')
      const value = saved && typeof saved === 'object' ? saved as { index?: unknown; revealed?: unknown } : {}
      const position = typeof value.index === 'number' && Number.isSafeInteger(value.index) ? value.index : 0
      setIndex(Math.min(Math.max(0, position), Math.max(0, total - 1)))
      setRevealed(value.revealed === true)
    } catch { setIndex(0); setRevealed(false) }
    setLoadedKey(key)
  }, [key, resolvedNodeId, progress.data, total, loadedKey])
  useEffect(() => {
    if (index >= senses.length && cards.hasNextPage && !cards.isFetchingNextPage && !cards.isError) void cards.fetchNextPage()
  }, [index, senses.length, cards.hasNextPage, cards.isFetchingNextPage, cards.isError, cards.fetchNextPage, cards])
  useEffect(() => {
    if (!key || loading || error || loadedKey !== key) return
    try { localStorage.setItem(key, JSON.stringify({ index, revealed })) } catch { /* Browsing works without persistence. */ }
  }, [key, index, revealed, loading, error, loadedKey])
  const move = useCallback((delta: number) => {
    if (!senses.length || cards.isFetchingNextPage) return
    setIndex(value => Math.max(0, Math.min(total - 1, value + delta)))
    setRevealed(false)
  }, [senses.length, total, cards.isFetchingNextPage])
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
    <div className="flex items-center gap-4 min-w-0 [&_small]:flex-none [&_small]:text-xs [&_small]:text-muted-foreground [&_small]:tabular-nums max-[760px]:pr-3 max-[760px]:gap-1.5 max-[760px]:overflow-hidden"><div className="w-full h-2 bg-muted overflow-hidden [&_span]:block [&_span]:h-full [&_span]:bg-foreground [&_span]:transition-[width] [&_span]:duration-200 [&_span]:ease-out max-[760px]:min-w-[18px] motion-reduce:[&_span]:transition-none"><span style={{ width: `${senses.length ? (index + 1) / total * 100 : 0}%` }} /></div><small>{senses.length ? `${index + 1} / ${total}` : tLearning('zeroCards')}</small></div>
  </header>
    {loading ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1 className="shimmer text-foreground/70">{tLearning('preparingFlashcards')}</h1></div></section> : error ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>{tLearning('couldNotLoad')}</h1><p role="alert">{error}</p><Button asChild><Link href={backHref}>{tLearning('backToLibrary')}</Link></Button></div></section>
      : !sense ? <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8"><div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>{tLearning('noFlashcardsYet')}</h1><p>{tLearning('addMeaningsPrompt')}</p><Button asChild><Link href={backHref}>{tLearning('backToLibrary')}</Link></Button></div></section>
        : <div className="flex-1 min-h-0 flex flex-col items-center justify-center p-3 sm:p-5 md:p-6 overflow-hidden">
            <div className="w-[min(calc(100%-32px),1240px)] flex-1 min-h-0 grid grid-cols-[56px_minmax(0,1fr)_56px] content-center items-center gap-4 sm:gap-7 my-auto max-[760px]:w-full max-[760px]:grid-cols-[44px_minmax(0,1fr)_44px] max-[760px]:gap-2">
              <Button variant="outline" size="icon" className="size-14 rounded-none max-[760px]:size-11 border-foreground max-[760px]:col-start-1 max-[760px]:row-start-2" aria-label={tLearning('previousCard')} onClick={() => move(-1)} disabled={index === 0}><ArrowLeft aria-hidden="true" /></Button>
              <div className="h-[min(540px,calc(100svh-190px))] max-h-[560px] min-h-[300px] w-full max-[760px]:col-span-full max-[760px]:row-start-1"><Flashcard cardId={sense.sense_id} content={sense} ordinal={index + 1} revealed={revealed} onRevealedChange={setRevealed} /></div>
              <Button variant="outline" size="icon" className="size-14 rounded-none max-[760px]:size-11 border-foreground max-[760px]:col-start-3 max-[760px]:row-start-2" aria-label={tLearning('nextCard')} onClick={() => move(1)} disabled={index === total - 1 || cards.isFetchingNextPage}><ArrowRight aria-hidden="true" /></Button>
            </div>
            <p className="flex-none text-center text-muted-foreground text-[11px] mt-2 max-[760px]:mt-1">{tLearning('flashcardShortcuts')}</p>
          </div>}
  </main>
}
