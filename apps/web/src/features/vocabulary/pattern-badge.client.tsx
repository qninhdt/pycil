'use client'

import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { parsePatternTokens } from './pattern'
import { useCopyToClipboard } from '@/lib/use-copy-to-clipboard.client'
import { toast } from 'sonner'
import { useTranslations } from 'next-intl'

/**
 * Bauhaus-styled Grammar Pattern Chip
 * - Geometric modular blueprint badge with sharp corners (rounded-none).
 * - Blue square architectural indicator.
 * - Bold headword / lemma.
 * - Blueprint slot chips for variable arguments (e.g. [sb], [sth], [do]).
 * - Click to copy with accessible feedback.
 */
export function PatternBadge({
  pattern,
  lemma,
}: {
  pattern: string
  lemma?: string
}) {
  const { isCopied: copied, copyToClipboard } = useCopyToClipboard({ copiedDuration: 1600 })
  const t = useTranslations('dictionary')
  const [copyFailed, setCopyFailed] = useState(false)
  const tokens = parsePatternTokens(pattern, lemma)

  const handleCopy = async () => {
    if (await copyToClipboard(pattern)) {
      setCopyFailed(false)
      toast.success(t('patternCopied'))
    } else {
      setCopyFailed(true)
      toast.error(t('patternCopyFailed'))
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={handleCopy}
        className="group/pattern relative inline-flex items-center gap-1.5 px-2.5 py-1 text-xs border border-border bg-card/70 hover:border-foreground/50 hover:bg-accent/40 active:translate-y-px transition-all duration-150 rounded-none cursor-pointer text-left select-none focus-visible:outline-2 focus-visible:outline-ring"
        title={t('copyPattern', { pattern })}
        aria-label={t('grammarPattern', { pattern })}
      >
        {/* Bauhaus blue square motif (form follows function: blue = structure) */}
        <span
          className={`size-1.5 flex-none transition-colors duration-150 ${
            copied ? 'bg-success' : 'bg-art-blue group-hover/pattern:bg-art-blue'
          }`}
          aria-hidden="true"
        />

        <span className="inline-flex items-center gap-1 flex-wrap font-sans">
          {tokens.map((token, index) => {
            if (token.type === 'slot') {
              return (
                <span
                  key={index}
                  className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider text-art-blue bg-art-blue/10 border border-art-blue/30 rounded-none leading-none select-all"
                  title={t(token.slot.descriptionKey, { slot: token.slot.label })}
                  aria-label={t(token.slot.descriptionKey, { slot: token.slot.label })}
                >
                  {token.slot.label}
                </span>
              )
            }

            if (token.type === 'word') {
              return (
                <span
                  key={index}
                  className={
                    token.isLemma
                      ? 'font-bold text-foreground'
                      : token.isConnector
                        ? 'font-medium text-muted-foreground'
                        : 'font-semibold text-foreground/90'
                  }
                >
                  {token.text}
                </span>
              )
            }

            return (
              <span key={index} className="text-muted-foreground font-mono">
                {token.text}
              </span>
            )
          })}
        </span>
      </button>
      {copyFailed && <Input readOnly value={pattern} aria-label={t('grammarPattern', { pattern })} className="h-8 w-full font-mono text-xs" onFocus={event => event.currentTarget.select()} />}
    </span>
  )
}

export function PatternList({
  patterns,
  lemma,
}: {
  patterns: string[]
  lemma?: string
}) {
  const t = useTranslations('dictionary')
  if (patterns.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 items-center" role="list" aria-label={t('grammarPatterns')}>
      {patterns.map(pattern => (
        <span role="listitem" key={pattern}><PatternBadge pattern={pattern} lemma={lemma} /></span>
      ))}
    </div>
  )
}
