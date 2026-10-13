import type { Messages } from '@/lib/preferences/locale'

export interface SlotMeta {
  code: string
  label: string
  descriptionKey: keyof Messages['dictionary']
}

export const KNOWN_SLOTS: Record<string, SlotMeta> = {
  sb: { code: 'sb', label: 'sb', descriptionKey: 'slotSomebody' },
  sth: { code: 'sth', label: 'sth', descriptionKey: 'slotSomething' },
  'sb/sth': { code: 'sb/sth', label: 'sb/sth', descriptionKey: 'slotSomebodyOrSomething' },
  'sth/sb': { code: 'sth/sb', label: 'sth/sb', descriptionKey: 'slotSomethingOrSomebody' },
  do: { code: 'do', label: 'do', descriptionKey: 'slotBaseVerb' },
  doing: { code: 'doing', label: 'doing', descriptionKey: 'slotGerund' },
  'doing sth': { code: 'doing sth', label: 'doing sth', descriptionKey: 'slotGerundObject' },
  'do sth': { code: 'do sth', label: 'do sth', descriptionKey: 'slotVerbObject' },
  done: { code: 'done', label: 'done', descriptionKey: 'slotParticiple' },
  oneself: { code: 'oneself', label: 'oneself', descriptionKey: 'slotReflexive' },
  "one's": { code: "one's", label: "one's", descriptionKey: 'slotPossessive' },
  clause: { code: 'clause', label: 'clause', descriptionKey: 'slotClause' },
  that: { code: 'that', label: 'that...', descriptionKey: 'slotThat' },
  'wh-': { code: 'wh-', label: 'wh-...', descriptionKey: 'slotWh' },
  adj: { code: 'adj', label: 'adj', descriptionKey: 'slotAdjective' },
  adv: { code: 'adv', label: 'adv', descriptionKey: 'slotAdverb' },
  num: { code: 'num', label: 'num', descriptionKey: 'slotNumber' },
  place: { code: 'place', label: 'place', descriptionKey: 'slotPlace' },
  prep: { code: 'prep', label: 'prep', descriptionKey: 'slotPreposition' },
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
        descriptionKey: 'slotPlaceholder',
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

