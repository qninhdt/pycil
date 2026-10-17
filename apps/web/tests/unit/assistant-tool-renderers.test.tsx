import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect,test } from 'vitest'
import { ToolBodyContent } from '../../src/features/assistant/tool-renderers.client'

function render(toolName: string, result: unknown, args: object = {}) {
  return renderToStaticMarkup(React.createElement(ToolBodyContent, {
    toolName, args, result, status: { type: 'complete' }, meta: { title: toolName },
  }))
}

test('learning progress shows backend counts and actual review recency', () => {
  const summary = { node_id: 'library', as_of: '2026-10-09T00:00:00Z', total: 0, new: 0, studied: 0, due: 0, not_due: 0, last_studied_at: null, reachable_decks: 0 }
  const html = render('learning_overview', { summaries: [summary] })
  expect(html).toContain('No reviews yet')
  expect(html).not.toContain('91%')
  expect(html).not.toContain('2 hours ago')
  expect(html.match(/>0<\/div>/g)).toHaveLength(3)
  const reviewed = render('learning_overview', { summaries: [{ ...summary, last_studied_at: '2026-10-08T12:00:00Z' }] })
  expect(reviewed).toContain('2026-10-08T12:00:00Z')
  expect(render('learning_overview', {})).toContain('Progress unavailable')
})

test('node metadata does not invent deck membership or folder type', () => {
  const html = render('read_library', { node: { name: 'Vocabulary', type: 'folder', parent_id: 'parent-id', path: [{ node_id: 'parent-id', name: 'Library' }] }, nodes: [], next_cursor: null })
  expect(html).toContain('Folder')
  expect(html).toContain('Library')
  expect(html).not.toContain('Flashcard Deck')
  expect(html).not.toContain('0 cards')
  expect(render('read_library', { node: { name: 'Bank', type: 'deck', parent_id: null }, senses: [] })).not.toContain('0 cards')
})

test('create node reports its returned type and destination', () => {
  const html = render('create_node', { name: 'Vocabulary', type: 'folder', parent_id: 'published-root' }, { name: 'Vocabulary', type: 'folder', parent_id: 'published-root' })
  expect(html).toContain('Created Folder')
  expect(html).toContain('published-root')
  expect(html).not.toContain('Created Deck')
  expect(html).not.toContain('Personal')
})


test('deck content shows senses and partial batch failures remain visible', () => {
  const html = render('read_library', { node: { name: 'Hello', type: 'deck' }, summary: { total: 13 }, senses: [{ sense_id: 1, lemma: 'bank', pos: 'noun', definition: 'a financial institution', examples: ['I went to the bank.'], learning: { state: 'new' } }], next_cursor: 'page-2' })
  expect(html).toContain('13 cards')
  expect(html).toContain('a financial institution')
  expect(html).toContain('I went to the bank.')
  expect(html).toContain('More results available')
  expect(html).not.toContain('No folders or decks found')
  expect(render('search_nodes', {})).toContain('Library results unavailable')
  expect(render('read_vocabulary', {})).toContain('Vocabulary unavailable')
  const batch = render('copy_nodes', { items: [{ name: 'Hello', status: 'succeeded' }, { source_node_id: 'other', status: 'failed', error: 'node_not_found' }] })
  expect(batch).toContain('succeeded')
  expect(batch).toContain('failed')
  expect(batch).toContain('node_not_found')
})

test('word search renders lexical results', () => {
  expect(render('search_words', { items: [
    { kind: 'word', word_id: 1, lemma: 'wizard', entry_type: 'word', match_kind: 'exact', matched_surface: 'wizard' },
  ] }, { queries: ['wizard'] })).toContain('wizard')
})


test('generation references and completed senses remain visible', () => {
  expect(render('search_words', { items: [
    { kind: 'reference', reference_id: 'entry_bank', display: 'bank', entry_type: 'word', match_kind: 'exact', matched_surface: 'bank' },
  ] })).toContain('Available to generate')
  expect(render('generate_words', { items: [{ job_id: 'pending' }, { error: 'invalid_reference' }] })).toContain('invalid_reference')
  expect(render('generate_words', { items: [{ status: 'running' }, { status: 'succeeded', senses: [{ sense_id: 1, lemma: 'bank', pos: 'noun', definition: 'a financial institution' }] }] })).toContain('a financial institution')
})
