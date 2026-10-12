import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import { test, expect } from '@playwright/test'

let render: (toolName: string, result: unknown, args?: object) => string

test.beforeAll(async () => {
  const built = await build({ stdin: { contents: `
    import React from 'react';
    import { renderToStaticMarkup } from 'react-dom/server';
    import { ToolBodyContent } from './src/components/assistant-ui/tool-renderers';
    export function render(toolName, result, args = {}) {
      return renderToStaticMarkup(React.createElement(ToolBodyContent, { toolName, args, result, status: { type: 'complete' }, meta: { title: toolName } }));
    }
  `, resolveDir: process.cwd() }, bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react-dom'] })
  const module = { exports: {} as { render: typeof render } }
  runInNewContext(built.outputFiles[0].text, { module, exports: module.exports, require: createRequire(import.meta.url) })
  render = module.exports.render
})

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
  const html = render('read_library', { node: { name: 'Vocabulary', type: 'FOLDER', parent_id: 'parent-id', path: [{ node_id: 'parent-id', name: 'Library' }] }, nodes: [], next_cursor: null })
  expect(html).toContain('Folder')
  expect(html).toContain('Library')
  expect(html).not.toContain('Flashcard Deck')
  expect(html).not.toContain('0 cards')
  expect(render('read_library', { node: { name: 'Bank', type: 'DECK', parent_id: null }, senses: [] })).not.toContain('0 cards')
})

test('create node reports its returned type and destination', () => {
  const html = render('create_node', { name: 'Vocabulary', type: 'FOLDER', parent_id: 'published-root' }, { name: 'Vocabulary', type: 'FOLDER', parent_id: 'published-root' })
  expect(html).toContain('Created Folder')
  expect(html).toContain('published-root')
  expect(html).not.toContain('Created Deck')
  expect(html).not.toContain('Personal')
})


test('deck content shows senses and partial batch failures remain visible', () => {
  const html = render('read_library', { node: { name: 'Hello', type: 'DECK' }, summary: { total: 13 }, senses: [{ sense_id: 1, lemma: 'bank', pos: 'NOUN', definition: 'a financial institution', examples: ['I went to the bank.'], learning: { state: 'NEW' } }], next_cursor: 'page-2' })
  expect(html).toContain('13 cards')
  expect(html).toContain('a financial institution')
  expect(html).toContain('I went to the bank.')
  expect(html).toContain('More results available')
  expect(html).not.toContain('No folders or decks found')
  expect(render('search_nodes', {})).toContain('Library results unavailable')
  expect(render('read_vocabulary', {})).toContain('Vocabulary unavailable')
  const batch = render('copy_nodes', { items: [{ name: 'Hello', status: 'SUCCEEDED' }, { source_node_id: 'other', status: 'FAILED', error: 'node_not_found' }] })
  expect(batch).toContain('SUCCEEDED')
  expect(batch).toContain('FAILED')
  expect(batch).toContain('node_not_found')
})

test('word generation renders JSON results, pending states and explicit malformed output', () => {
  const html = render('generate_words', JSON.stringify({ items: [
    { target: 'wizard', lemma: 'wizard', status: 'SUCCEEDED', task_id: 'task', senses: [
      { sense_id: 19404, lemma: 'wizard', pos: 'NOUN', definition: 'A person with magical powers.' },
    ] },
    { target: 'wand', status: 'RUNNING', task_id: 'waiting' },
    { target: 'missing', status: 'FAILED', error: 'generation_failed' },
  ] }), { words: ['wizard', 'wand', 'missing'] })
  expect(html).toContain('A person with magical powers.')
  expect(html).toContain('RUNNING')
  expect(html).toContain('generation_failed')
  expect(render('generate_words', 'invalid provider output')).toContain('Vocabulary preparation unavailable.')
  expect(render('search_words', { items: [
    { kind: 'WORD', word_id: 1, lemma: 'wizard', entry_type: 'WORD', match_kind: 'EXACT', matched_surface: 'wizard' },
  ] }, { queries: ['wizard'] })).toContain('wizard')
})
