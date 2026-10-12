'use client'

import type { CSSProperties } from 'react'
import { Badge } from '@/components/ui/badge'
import { Background } from '@/components/artwork/artwork'
import { MarkedText } from '@/components/content/marked-text'
import { flashcardArtwork } from '@/lib/flashcard-artwork'

// Presentation only: no queries, session state, learning submission or fullscreen shell.
// Both the Deck preview and a future focus-mode player can own this same two-face card.
export type FlashcardContent = {
  lemma: string; pos: string; definition: string | null
  examples: ({ text: string } | { content: string })[]; cefr_level?: string | null; pronunciation?: string | null
}
export type FlashcardProps = {
  cardId: string | number
  content: FlashcardContent
  revealed: boolean
  onRevealedChange: (revealed: boolean) => void
  ordinal: number
}

import { useTranslations } from 'next-intl'

export function Flashcard({ cardId, content, revealed, onRevealedChange, ordinal }: FlashcardProps) {
  const t = useTranslations('learning')
  const wordScale = Math.min(1, 8 / [...content.lemma].length)
  const artwork = flashcardArtwork(cardId)
  return <article className="@container/flashcard relative isolate grid min-w-0 h-full overflow-hidden border border-foreground bg-background text-foreground" data-face={revealed ? 'back' : 'front'} aria-label={`Flashcard for ${content.lemma}`}
    data-artwork={artwork} style={{ '--flashcard-word-scale': wordScale } as CSSProperties}>
    <div className="pointer-events-none absolute inset-0 -z-10 after:absolute after:inset-0 after:bg-[color-mix(in_srgb,var(--background)_82%,transparent)] after:content-['']" aria-hidden="true"><Background name={artwork} className="h-full w-full" /></div>
    <span className="absolute top-8 right-10 text-[11px] font-semibold uppercase tracking-[.16em] text-muted-foreground @max-[440px]/flashcard:top-6 @max-[440px]/flashcard:right-6 @max-[440px]/flashcard:text-[10px]">{content.pos}</span>
    <div className={`relative col-start-1 row-start-1 grid h-full min-h-[360px] min-w-0 items-center px-10 pt-[72px] pb-[88px] text-center @max-[440px]/flashcard:min-h-[300px] @max-[440px]/flashcard:px-6 @max-[440px]/flashcard:pt-16 @max-[440px]/flashcard:pb-20 ${revealed ? 'invisible pointer-events-none' : ''}`} aria-hidden={revealed} inert={revealed}>
      <div className="relative min-w-0 max-w-full"><h3 className="text-[clamp(18px,calc(12cqi*var(--flashcard-word-scale)),96px)] font-extrabold leading-[1.1] tracking-[-.04em] wrap-anywhere text-balance">{content.lemma}</h3>{content.pronunciation && <p className="mt-4 text-[clamp(16px,3cqi,24px)] leading-[1.5] text-muted-foreground">{content.pronunciation}</p>}</div>
    </div>
    <div className={`col-start-1 row-start-1 flex h-full min-h-[360px] min-w-0 flex-col overflow-hidden px-10 pt-10 pb-14 @max-[440px]/flashcard:min-h-[300px] @max-[440px]/flashcard:px-6 @max-[440px]/flashcard:pt-7 @max-[440px]/flashcard:pb-10 ${!revealed ? 'invisible pointer-events-none' : ''}`} aria-hidden={!revealed} inert={!revealed}>
      <header className="relative mb-7 min-h-12 pr-16 [&_[data-slot=badge]]:mt-3  @max-[440px]/flashcard:mb-6"><h3 className="text-[clamp(18px,calc(6cqi*var(--flashcard-word-scale)),48px)] font-extrabold leading-[1.15] tracking-[-.03em] wrap-anywhere">{content.lemma}</h3>
        {content.pronunciation && <p className="mt-4 text-[clamp(16px,3cqi,24px)] leading-[1.5] text-muted-foreground">{content.pronunciation}</p>}
        {content.cefr_level && <Badge variant="secondary">{content.cefr_level}</Badge>}
      </header>
      <div className="grid flex-1 min-h-0 grid-cols-[auto_minmax(0,1fr)] gap-5 overflow-y-auto pr-1 @max-[440px]/flashcard:gap-3"><span className="text-[clamp(28px,7cqi,44px)] font-extrabold leading-[1.1] tracking-[-.03em] text-muted-foreground tabular-nums sticky top-0" aria-label={t('cardOrdinal', { ordinal })}>{String(ordinal).padStart(2, '0')}</span>
        <div className="min-w-0 border-l border-border pl-5 @max-[440px]/flashcard:pl-3"><p className="max-w-[44ch] text-[clamp(18px,3.6cqi,28px)] font-[750] leading-[1.4] tracking-[-.02em] wrap-anywhere text-pretty"><MarkedText text={content.definition ?? t('definitionUnavailable')} /></p>
          {content.examples.map((example, index) => {
            const exampleText = ('text' in example && example.text) || ('content' in example && example.content) || ''
            return <blockquote key={index} className="relative mt-5 pl-4 text-[clamp(14px,2.5cqi,18px)] italic leading-[1.7] text-muted-foreground wrap-anywhere before:absolute before:top-1 before:bottom-1 before:left-0 before:w-[2px] before:bg-art-blue before:content-[''] @max-[440px]/flashcard:pl-3"><MarkedText text={exampleText} /></blockquote>
          })}
        </div>
      </div>
    </div>
    <button type="button" className="group absolute inset-0 h-full w-full cursor-pointer rounded-none border-0 bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset forced-colors:focus-visible:outline-2 forced-colors:focus-visible:-outline-offset-4 forced-colors:focus-visible:outline-[Highlight]" onClick={() => onRevealedChange(!revealed)} aria-label={revealed ? t('flipBack', { word: content.lemma }) : t('revealMeaning', { word: content.lemma })}>
      {!revealed && <span className="absolute right-10 bottom-12 left-10 text-[11px] uppercase tracking-[.24em] text-muted-foreground group-hover:text-foreground @max-[440px]/flashcard:right-6 @max-[440px]/flashcard:bottom-10 @max-[440px]/flashcard:left-6 @max-[440px]/flashcard:text-[10px] @max-[440px]/flashcard:tracking-[.18em]">{t('tapToReveal')}</span>}
    </button>
  </article>
}
