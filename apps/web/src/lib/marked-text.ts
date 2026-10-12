// Mirrors the bundled backend's lexi_ai/text.py parse_marked_example protocol.
// Inflection codes accept either case; learner text is preserved.
export const targetInflections = ['base', 'past', 'past_participle', 'present_3sg', 'ing', 'plural', 'comparative', 'superlative'] as const
export type TargetInflection = typeof targetInflections[number]
export type TargetSpan = { surface: string; inf: TargetInflection; start: number; end: number }
export type ParsedMarkedText = { text: string; spans: TargetSpan[]; valid: boolean }

const codes: Record<string, TargetInflection> = {
  '': 'base',
  b: 'base',
  base: 'base',
  p: 'past',
  past: 'past',
  pp: 'past_participle',
  past_participle: 'past_participle',
  '3': 'present_3sg',
  '3sg': 'present_3sg',
  present_3sg: 'present_3sg',
  ing: 'ing',
  pl: 'plural',
  plural: 'plural',
  c: 'comparative',
  comp: 'comparative',
  comparative: 'comparative',
  s: 'superlative',
  sup: 'superlative',
  superlative: 'superlative',
}

export function parseMarkedText(content: string): ParsedMarkedText {
  const invalid = (): ParsedMarkedText => ({ text: content ?? '', spans: [], valid: false })
  if (typeof content !== 'string') return { text: '', spans: [], valid: true }
  if ([...content].length > 16000) return invalid()

  const anyTargetTag = /[\[\]]/
  const tag = /\[([^\[\]|]+)(?:\|([a-z0-9_]+))?\]/gi

  if (anyTargetTag.test(content)) {
    const spans: TargetSpan[] = []
    let cursor = 0, clean = ''
    for (const match of content.matchAll(tag)) {
      const prefix = content.slice(cursor, match.index)
      const rawCode = (match[2] ?? '').trim().toLowerCase()
      const inf = codes[rawCode]
      if (anyTargetTag.test(prefix) || !inf || !match[1].trim()) return invalid()
      clean += prefix
      // Offsets address the JS string in UTF-16; no offsets are exchanged with the API.
      spans.push({ surface: match[1], inf, start: clean.length, end: clean.length + match[1].length })
      clean += match[1]
      cursor = match.index + match[0].length
    }
    const tail = content.slice(cursor)
    if (anyTargetTag.test(tail)) return invalid()
    return { text: clean + tail, spans, valid: true }
  }

  const mdBold = /\*\*([^*\n]+?)\*\*/g
  const boldMatches = [...content.matchAll(mdBold)]
  if (boldMatches.length > 0) {
    const spans: TargetSpan[] = []
    let cursor = 0, clean = ''
    for (const match of boldMatches) {
      const prefix = content.slice(cursor, match.index)
      if (!match[1].trim()) return invalid()
      clean += prefix
      spans.push({ surface: match[1], inf: 'base', start: clean.length, end: clean.length + match[1].length })
      clean += match[1]
      cursor = match.index + match[0].length
    }
    const tail = content.slice(cursor)
    return { text: clean + tail, spans, valid: true }
  }

  return { text: content, spans: [], valid: true }
}
