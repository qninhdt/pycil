'use client'

import { useState, type KeyboardEvent } from 'react'
import { ArrowLeft, ArrowRight } from '@/components/artwork/artwork'
import { Flashcard } from '@/features/study/flashcard.client'
import { Button } from '@/components/ui/button'
import { HomeFailure, HomeLoading } from '@/features/home/home-state.client'
import { useLibraryMeanings } from '@/features/library/use-library.client'
import { LibraryEmpty } from './library-shared.client'
import { useTranslations } from 'next-intl'

const pageSize = 12

export function LibraryFlashcardPreview({ nodeId, total }: { nodeId: string; total?: number }) {
  const t = useTranslations('library')
  const [cursors, setCursors] = useState<string[]>([])
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const query = useLibraryMeanings(nodeId, { cursor: cursors.at(-1), limit: pageSize })
  const senses = query.data?.senses ?? []
  const currentIndex = Math.min(index, Math.max(0, senses.length - 1))
  const sense = senses[currentIndex]
  const ordinal = cursors.length * pageSize + currentIndex + 1
  const previousDisabled = query.isFetching || !sense || cursors.length === 0 && currentIndex === 0
  const nextDisabled = query.isFetching || !sense || currentIndex === senses.length - 1 && !query.data?.next_cursor
  function previous() {
    if (previousDisabled) return
    setRevealed(false)
    if (currentIndex === 0) { setCursors(cursors.slice(0, -1)); setIndex(pageSize - 1) }
    else setIndex(currentIndex - 1)
  }
  function next() {
    if (nextDisabled) return
    setRevealed(false)
    if (currentIndex === senses.length - 1 && query.data?.next_cursor) { setCursors([...cursors, query.data.next_cursor]); setIndex(0) }
    else setIndex(currentIndex + 1)
  }
  function keyboard(event: KeyboardEvent<HTMLElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
    if (event.key === 'ArrowRight') { event.preventDefault(); next() }
    if (event.key === 'ArrowLeft') { event.preventDefault(); previous() }
  }
  return <section className="library-inline-preview @container/preview min-w-0" aria-label={t('flashcardPreview')} onKeyDown={keyboard} aria-busy={query.isFetching}>
    <div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2>{t('flashcardPreview')}</h2>{sense && <span className="text-muted-foreground text-xs tabular-nums" role="status">{ordinal}{total === undefined ? '' : ` / ${total}`}</span>}</div>
    {query.isError ? <HomeFailure label="flashcard preview" error={query.error} retry={() => { void query.refetch() }} /> : query.isPending ? <HomeLoading label="flashcard preview" /> : !sense ? <LibraryEmpty title={t('noWordsToPreview')} />
      : <div className="grid grid-cols-[40px_minmax(0,1fr)_40px] gap-3 items-center h-[420px] max-h-[420px] @max-[440px]/preview:h-[360px] @max-[440px]/preview:max-h-[360px] [&_>_article]:col-start-2 [&_>_article]:row-start-1 [&_>_article]:h-full">
         <Flashcard cardId={sense.sense_id} content={sense} ordinal={ordinal} revealed={revealed} onRevealedChange={setRevealed} />
        <Button variant="outline" size="icon" className="col-start-1 row-start-1" aria-label={t('previousFlashcard')} onClick={previous} disabled={previousDisabled}><ArrowLeft aria-hidden="true" /></Button>
        <Button variant="outline" size="icon" className="col-start-3 row-start-1" aria-label={t('nextFlashcard')} onClick={next} disabled={nextDisabled}><ArrowRight aria-hidden="true" /></Button>
      </div>}
  </section>
}
