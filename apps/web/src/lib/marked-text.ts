// Mirrors the bundled backend's lexi_ai/text.py parse_marked_example protocol.
// Tags are lowercase and exact, inflections are the eight lexi_ai/vocab.py values.
export const targetInflections = ['base', 'past', 'past_participle', 'present_3sg', 'ing', 'plural', 'comparative', 'superlative'] as const
export type TargetInflection = typeof targetInflections[number]
export type TargetSpan = { surface: string; inf: TargetInflection; start: number; end: number }
export type ParsedMarkedText = { text: string; spans: TargetSpan[]; valid: boolean }

export function parseMarkedText(content: string): ParsedMarkedText {
  const invalid = (): ParsedMarkedText => ({ text: content, spans: [], valid: false })
  if ([...content].length > 16000) return invalid()
  const tag = /<t inf="([a-z0-9_]+)">([^<>]+)<\/t>/g
  const anyTargetTag = /<\/?t(?=$|[^\p{L}\p{N}_])/iu
  const spans: TargetSpan[] = []
  let cursor = 0, clean = ''
  for (const match of content.matchAll(tag)) {
    const prefix = content.slice(cursor, match.index)
    if (anyTargetTag.test(prefix) || !targetInflections.includes(match[1] as TargetInflection) || !match[2].trim()) return invalid()
    clean += prefix
    // Offsets address the JS string in UTF-16; no offsets are exchanged with the API.
    spans.push({ surface: match[2], inf: match[1] as TargetInflection, start: clean.length, end: clean.length + match[2].length })
    clean += match[2]
    cursor = match.index + match[0].length
  }
  const tail = content.slice(cursor)
  if (anyTargetTag.test(tail)) return invalid()
  return { text: clean + tail, spans, valid: true }
}
