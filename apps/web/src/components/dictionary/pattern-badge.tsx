'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { useTranslations } from 'next-intl'

export interface SlotMeta {
  code: string
  label: string
  description: string
}

export const KNOWN_SLOTS: Record<string, SlotMeta> = {
  sb: { code: 'sb', label: 'sb', description: 'Somebody (person)' },
  sth: { code: 'sth', label: 'sth', description: 'Something (object or concept)' },
  'sb/sth': { code: 'sb/sth', label: 'sb/sth', description: 'Somebody or something' },
  'sth/sb': { code: 'sth/sb', label: 'sth/sb', description: 'Something or somebody' },
  do: { code: 'do', label: 'do', description: 'Verb (infinitive / base form)' },
  doing: { code: 'doing', label: 'doing', description: 'Verb (-ing / gerund form)' },
  'doing sth': { code: 'doing sth', label: 'doing sth', description: 'Verb (-ing) + something' },
  'do sth': { code: 'do sth', label: 'do sth', description: 'Verb + something' },
  done: { code: 'done', label: 'done', description: 'Verb (past participle)' },
  oneself: { code: 'oneself', label: 'oneself', description: 'Reflexive pronoun (oneself)' },
  "one's": { code: "one's", label: "one's", description: "Possessive determiner (one's)" },
  clause: { code: 'clause', label: 'clause', description: 'Clause (that...)' },
  that: { code: 'that', label: 'that...', description: 'That clause' },
  'wh-': { code: 'wh-', label: 'wh-...', description: 'Wh- question clause' },
  adj: { code: 'adj', label: 'adj', description: 'Adjective' },
  adv: { code: 'adv', label: 'adv', description: 'Adverb' },
  num: { code: 'num', label: 'num', description: 'Number or quantity' },
  place: { code: 'place', label: 'place', description: 'Place or location' },
  prep: { code: 'prep', label: 'prep', description: 'Preposition' },
}

export type PatternToken =
  | { type: 'slot'; slot: SlotMeta }
  | { type: 'word'; text: string; isLemma: boolean; isConnector: boolean }
  | { type: 'punct'; text: string }

const GRAMMAR_CONNECTORS = new Set([
  'to',
  'for',
  'on',
  'in',
  'at',
  'of',
  'with',
  'from',
  'as',
  'by',
  'about',
  'into',
  'over',
  'under',
  'through',
  'between',
  'against',
  'without',
  'after',
  'before',
  'a',
  'an',
  'the',
  'be',
  'is',
  'are',
  'was',
  'were',
])

export function parsePatternTokens(pattern: string, lemma?: string): PatternToken[] {
  const tokens: PatternToken[] = []
  const normLemma = lemma?.trim().toLowerCase()
  // Match slots in curly braces: {sth}, {sb}, {do}, etc.
  const regex = /\{([^}]+)\}|([a-zA-Z0-9'-]+)|([^\s\w{}]+)/g
  let match: RegExpExecArray | null

  while ((match = regex.exec(pattern)) !== null) {
    if (match[1] !== undefined) {
      const rawSlot = match[1].trim()
      const slotLower = rawSlot.toLowerCase()
      const meta = KNOWN_SLOTS[slotLower] ?? {
        code: slotLower,
        label: rawSlot,
        description: `Placeholder: ${rawSlot}`,
      }
      tokens.push({ type: 'slot', slot: meta })
    } else if (match[2] !== undefined) {
      const word = match[2]
      const lower = word.toLowerCase()
      const isLemma = Boolean(normLemma && lower === normLemma)
      const isConnector = GRAMMAR_CONNECTORS.has(lower)
      tokens.push({ type: 'word', text: word, isLemma, isConnector })
    } else if (match[3] !== undefined) {
      tokens.push({ type: 'punct', text: match[3] })
    }
  }

  return tokens
}

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
  const [copied, setCopied] = useState(false)
  const t = useTranslations('dictionary')
  const tokens = parsePatternTokens(pattern, lemma)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(pattern)
      setCopied(true)
      toast.success(t('patternCopied'))
      setTimeout(() => setCopied(false), 1600)
    } catch {
      // Fallback
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="group/pattern relative inline-flex items-center gap-1.5 px-2.5 py-1 text-xs border border-border bg-card/70 hover:border-foreground/50 hover:bg-accent/40 active:translate-y-px transition-all duration-150 rounded-none cursor-pointer text-left select-none focus-visible:outline-2 focus-visible:outline-ring"
      title={`${pattern} · Click to copy`}
      aria-label={`Grammar pattern: ${pattern}`}
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
                title={token.slot.description}
                aria-label={token.slot.description}
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
  )
}

export function PatternList({
  patterns,
  lemma,
}: {
  patterns: string[]
  lemma?: string
}) {
  if (!patterns || patterns.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2 items-center" role="list" aria-label="Grammar patterns">
      {patterns.map(pattern => (
        <PatternBadge key={pattern} pattern={pattern} lemma={lemma} />
      ))}
    </div>
  )
}
