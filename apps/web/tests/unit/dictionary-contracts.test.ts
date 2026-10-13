import { expect,test } from 'vitest'

import { MatchKind,parseWordSearch } from '../../src/lib/api/vocabulary'

test('search parser preserves mixed ranking and validates classified hits', () => {
  const response = { items: [
    { kind: 'reference', reference_id: 'entry_opaque', display: 'orbit', entry_type: 'word', match_kind: 'exact', matched_surface: 'orbit' },
    { kind: 'word', word_id: 10, lemma: 'orbital', entry_type: 'word', match_kind: 'prefix', matched_surface: 'orbital' },
  ] }
  const parsed = parseWordSearch(response)
  expect(parsed.items.map(hit => hit.kind)).toEqual(['reference', 'word'])
  expect(parsed.items[0].match_kind).toBe(MatchKind.EXACT)
  expect(parseWordSearch({ items: [] })).toEqual({ items: [] })
  expect(() => parseWordSearch({ words: [], references: [] })).toThrow()
  for (const match_kind of ['FORM', 'UNKNOWN', null]) {
    expect(() => parseWordSearch({ items: [{ ...response.items[0], match_kind }] })).toThrow()
  }
  expect(() => parseWordSearch({ items: [{ ...response.items[0], kind: 'CAMBRIDGE' }] })).toThrow()
})
