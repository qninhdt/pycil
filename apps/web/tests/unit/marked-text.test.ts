import database from '../../src/lib/services/mock/database.json' with { type: 'json' }

import { expect,test } from 'vitest'

import { parseMarkedText,targetInflections } from '../../src/lib/marked-text'

import { parseDictionaryWord } from '../../src/lib/dictionary-model'

test('marked text follows backend inflections, repeated/discontinuous targets and Unicode', () => {
  const codes = ['', 'p', 'pp', '3', 'ing', 'pl', 'c', 's']
  for (const [index, inf] of targetInflections.entries()) {
    for (const label of [codes[index], codes[index].toUpperCase()]) {
      const parsed = parseMarkedText(`Before [Target${label ? '|' + label : ''}] after.`)
      expect(parsed).toEqual({ valid: true, text: 'Before Target after.', spans: [{ surface: 'Target', inf, start: 7, end: 13 }] })
    }
  }
  const split = parseMarkedText('She [gave|p] it [up], then [gave up|p] again.')
  expect(split.text).toBe('She gave it up, then gave up again.')
  expect(split.spans.map(span => span.surface)).toEqual(['gave', 'up', 'gave up'])
  const unicode = parseMarkedText('🌍 [café] — café.')
  expect(unicode.spans.map(span => unicode.text.slice(span.start, span.end))).toEqual(['café'])
  expect(parseMarkedText('a word with no markup')).toEqual({ text: 'a word with no markup', spans: [], valid: true })
  for (const sense of database.dictionary.words.map(parseDictionaryWord).flatMap(word => word.senses)) {
    const parsed = parseMarkedText(sense.examples[0].content)
    expect(parsed.valid).toBe(true)
    expect(parsed.spans.length).toBeGreaterThan(0)
  }
})

test('malformed markup remains literal, without partially trusted targets or HTML execution', () => {
  const invalid = ['[word|unknown]', '[ ]', '[word', '[[word]]', '[word|]', '[good][bad', 'x'.repeat(16001)]
  for (const text of invalid) expect(parseMarkedText(text)).toEqual({ text, spans: [], valid: false })
  const html = '<script>alert(1)</script> <img src=x onerror=alert(1)>'
  expect(parseMarkedText(html)).toEqual({ text: html, spans: [], valid: true }) // Rendered as React text, never HTML.
})
