import { expect,test } from 'vitest'

import { libraryHref,publishedHref, publicCollectionHref, nodeHref } from '../../src/features/library/model'
import { paginationHref } from '../../src/lib/query/url'

import { parseMeaningPage,parseNodeDetails } from '../../src/lib/api/library'

test('live lexical examples read native content and retain backend target markup', () => {
  const content = 'They [abandoned|p] the car.'
  const page = parseMeaningPage({ senses: [{ sense_id: 8, lemma: 'abandon', pos: 'verb', definition: 'to leave permanently', cefr_level: 'b1',
    learning: null, examples: [{ id: 91, content, theme_id: null }], sources: [], sources_has_more: false }], next_cursor: null })
  expect(page.senses[0].examples).toEqual([{ text: content }])
})

test('Library contracts reject incomplete DTOs and links safely encode node identities', () => {
  expect(() => parseNodeDetails({ id: 'node' })).toThrow()
  expect(() => parseMeaningPage({ senses: [{ sense_id: -1 }], next_cursor: null })).toThrow()
  expect(() => parseMeaningPage({ senses: [{ sense_id: 1, lemma: 'bank', pos: 'noun', definition: 'a bank', learning: { state: 'MASTERED' } }], next_cursor: null })).toThrow()
  expect(libraryHref('a&tab=bad', 'words')).toBe('/app/personal/a%26tab%3Dbad/words')
  expect(libraryHref('a/b?#', 'overview')).toBe('/app/personal/a%2Fb%3F%23')
  expect(libraryHref('everyday')).toBe('/app/personal/everyday')
  expect(libraryHref('everyday', 'overview')).toBe('/app/personal/everyday')
  expect(libraryHref()).toBe('/app/personal')
  expect(publishedHref('node ?', 'words')).toBe('/app/published/node%20%3F/words')
  expect(publicCollectionHref('sam', 'deck/a', 'words')).toBe('/u/sam/deck%2Fa/words')
  expect(nodeHref({ id: 'deck', owner_id: 'sam', space: 'published' }, 'words')).toBe('/u/sam/deck/words')
  expect(paginationHref('/u/sam/deck/words', new URLSearchParams('q=bank&cursor=old'), ['old', 'next+one'])).toBe('/u/sam/deck/words?q=bank&cursor=old&cursor=next%2Bone')
  expect(parseMeaningPage({ senses: [], next_cursor: null }).senses).toEqual([])
})
