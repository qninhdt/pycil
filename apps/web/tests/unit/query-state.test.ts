import { expect, test } from 'vitest'
import { dehydrate, hydrate } from '@tanstack/react-query'
import { invalidateLibrary } from '../../src/features/library/invalidate'
import { makeQueryClient } from '../../src/lib/query/client'
import { dictionaryState } from '../../src/features/vocabulary/queries'
import { contentsOptions, meaningOptions } from '../../src/features/library/queries'
import { discoveryState } from '../../src/features/library/discovery-queries'
import { searchParams } from '../../src/lib/query/url'

test('URL normalization selects current cursor and rejects unsupported query values', () => {
  const params = searchParams({ q: ' bank ', cursor: ['first', 'second'], state: 'invented', sort: 'invented', word: '0', type: 'deck' })
  expect(contentsOptions(params)).toEqual({ q: 'bank', cursor: 'second', limit: 12 })
  expect(meaningOptions(params)).toEqual({ q: 'bank', cursor: 'second', limit: 12, state: 'all', sort: 'lemma_asc' })
  expect(discoveryState(params)).toEqual({ q: 'bank', type: 'deck', cursor: 'second' })
  expect(dictionaryState(params)).toEqual({ query: 'bank', wordId: null })
  expect(dictionaryState(new URLSearchParams('word=12'))).toEqual({ query: '', wordId: 12 })
})

test('fresh hydration serves the initial result while invalidated data can refetch', async () => {
  const server = makeQueryClient(), browser = makeQueryClient(), key = ['live', 'session-A', 'account']
  server.setQueryData(key, { name: 'Learner' })
  hydrate(browser, dehydrate(server))
  let reads = 0
  const query = { queryKey: key, queryFn: async () => { reads++; return { name: 'Updated' } } }
  expect(await browser.query(query)).toEqual({ name: 'Learner' })
  expect(reads).toBe(0)
  await browser.invalidateQueries({ queryKey: key })
  expect(await browser.query(query)).toEqual({ name: 'Updated' })
  expect(reads).toBe(1)
  expect(makeQueryClient().getQueryData(key)).toBeUndefined()
  server.clear(); browser.clear()
})


test('a Library write refreshes affected data within the active session', async () => {
  const client = makeQueryClient()
  const changed = ['library-node', 'node-progress', 'flashcards', 'destination', 'dictionary-context']
  for (const resource of [...changed, 'account', 'assistant-conversations']) {
    client.setQueryData(['live', 'session-A', resource], { saved: true })
    client.setQueryData(['live', 'session-B', resource], { saved: true })
  }
  await invalidateLibrary(client, 'live', 'session-A')
  for (const resource of changed) {
    expect(client.getQueryState(['live', 'session-A', resource])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['live', 'session-B', resource])?.isInvalidated).toBe(false)
  }
  expect(client.getQueryState(['live', 'session-A', 'account'])?.isInvalidated).toBe(false)
  expect(client.getQueryState(['live', 'session-A', 'assistant-conversations'])?.isInvalidated).toBe(false)
  client.clear()
})
