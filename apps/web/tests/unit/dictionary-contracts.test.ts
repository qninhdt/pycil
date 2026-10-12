import { expect,test } from 'vitest'

import { MatchKind,parseWordSearch } from '../../src/lib/dictionary-model'

test('search parser preserves mixed ranking and validates classified hits', () => {
  const response = { items: [
    { kind: 'REFERENCE', reference_id: 'entry_opaque', display: 'orbit', entry_type: 'WORD', match_kind: 'EXACT', matched_surface: 'orbit' },
    { kind: 'WORD', word_id: 10, lemma: 'orbital', entry_type: 'WORD', match_kind: 'PREFIX', matched_surface: 'orbital' },
  ] }
  const parsed = parseWordSearch(response)
  expect(parsed.items.map(hit => hit.kind)).toEqual(['REFERENCE', 'WORD'])
  expect(parsed.items[0].match_kind).toBe(MatchKind.EXACT)
  expect(parseWordSearch({ items: [] })).toEqual({ items: [] })
  expect(() => parseWordSearch({ words: [], references: [] })).toThrow()
  for (const match_kind of ['FORM', 'UNKNOWN', null]) {
    expect(() => parseWordSearch({ items: [{ ...response.items[0], match_kind }] })).toThrow()
  }
  expect(() => parseWordSearch({ items: [{ ...response.items[0], kind: 'CAMBRIDGE' }] })).toThrow()
})
