// @vitest-environment happy-dom
import React from 'react'
import { afterEach, expect, test } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ToolBodyContent } from '../../src/features/assistant/tool-renderers.client'

afterEach(() => {
  cleanup()
})

function renderTool(toolName: string, result: unknown, args: object = {}) {
  cleanup()
  return render(
    React.createElement(ToolBodyContent, {
      toolName,
      args,
      result,
      status: { type: 'complete' },
      meta: { title: toolName },
    }),
  )
}

test('learning progress shows backend counts and actual review recency', () => {
  const summary = {
    node_id: 'library',
    as_of: '2026-10-09T00:00:00Z',
    total: 0,
    new: 0,
    studied: 0,
    due: 0,
    not_due: 0,
    last_studied_at: null,
    reachable_decks: 0,
  }
  renderTool('learning_overview', { summaries: [summary] })
  expect(screen.getByText(/No reviews yet/)).toBeDefined()
  expect(screen.queryByText('91%')).toBeNull()
  expect(screen.queryByText('2 hours ago')).toBeNull()

  // Three zero count indicators for Due, New, Studied
  const zeroCounts = screen.getAllByText('0')
  expect(zeroCounts).toHaveLength(3)
  expect(screen.getByText('Due')).toBeDefined()
  expect(screen.getByText('New')).toBeDefined()
  expect(screen.getByText('Studied')).toBeDefined()

  renderTool('learning_overview', {
    summaries: [{ ...summary, last_studied_at: '2026-10-08T12:00:00Z' }],
  })
  const timeElement = document.querySelector('time[dateTime="2026-10-08T12:00:00Z"]')
  expect(timeElement).not.toBeNull()
  expect(screen.queryByText(/No reviews yet/)).toBeNull()

  renderTool('learning_overview', {})
  expect(screen.getByText(/Progress unavailable/)).toBeDefined()
})

test('node metadata does not invent deck membership or folder type', () => {
  renderTool('read_library', {
    node: {
      name: 'Vocabulary',
      type: 'folder',
      parent_id: 'parent-id',
      path: [{ node_id: 'parent-id', name: 'Library' }],
    },
    nodes: [],
    next_cursor: null,
  })

  expect(screen.getByRole('heading', { level: 4, name: 'Vocabulary' })).toBeDefined()
  expect(screen.getByText('Folder')).toBeDefined()
  expect(screen.getByText(/Parent:\s*Library/)).toBeDefined()
  expect(screen.queryByText('Flashcard Deck')).toBeNull()
  expect(screen.queryByText('0 cards')).toBeNull()

  renderTool('read_library', {
    node: { name: 'Bank', type: 'deck', parent_id: null },
    senses: [],
  })
  expect(screen.queryByText('0 cards')).toBeNull()
})

test('create node reports its returned type and destination', () => {
  renderTool(
    'create_node',
    { name: 'Vocabulary', type: 'folder', parent_id: 'published-root' },
    { name: 'Vocabulary', type: 'folder', parent_id: 'published-root' },
  )

  expect(screen.getByText(/Created Folder: "Vocabulary"/)).toBeDefined()
  expect(screen.getByText(/Target location: published-root/)).toBeDefined()
  expect(screen.queryByText(/Created Deck/)).toBeNull()
  expect(screen.queryByText(/Personal/)).toBeNull()
})

test('deck content shows senses and partial batch failures remain visible', () => {
  renderTool('read_library', {
    node: { name: 'Hello', type: 'deck' },
    summary: { total: 13 },
    senses: [
      {
        sense_id: 1,
        lemma: 'bank',
        pos: 'noun',
        definition: 'a financial institution',
        examples: ['I went to the bank.'],
        learning: { state: 'new' },
      },
    ],
    next_cursor: 'page-2',
  })

  expect(screen.getByText(/13\s+cards/)).toBeDefined()
  expect(screen.getByText('a financial institution')).toBeDefined()
  expect(screen.getByText('I went to the bank.')).toBeDefined()
  expect(screen.getByText(/More results available/)).toBeDefined()
  expect(screen.queryByText('No folders or decks found')).toBeNull()

  renderTool('search_nodes', {})
  expect(screen.getByText(/Library results unavailable/)).toBeDefined()

  renderTool('read_vocabulary', {})
  expect(screen.getByText(/Vocabulary unavailable/)).toBeDefined()

  renderTool('copy_nodes', {
    items: [
      { name: 'Hello', status: 'succeeded' },
      { source_node_id: 'other', status: 'failed', error: 'node_not_found' },
    ],
  })
  expect(screen.getByText(/succeeded/)).toBeDefined()
  expect(screen.getByText(/failed/)).toBeDefined()
  expect(screen.getByText(/node_not_found/)).toBeDefined()
})

test('word search renders lexical results', () => {
  renderTool(
    'search_words',
    {
      items: [
        {
          kind: 'word',
          word_id: 1,
          lemma: 'wizard',
          entry_type: 'word',
          match_kind: 'exact',
          matched_surface: 'wizard',
        },
      ],
    },
    { queries: ['wizard'] },
  )

  expect(screen.getByText('wizard')).toBeDefined()
})

test('generation references and completed senses remain visible', () => {
  renderTool('search_words', {
    items: [
      {
        kind: 'reference',
        reference_id: 'entry_bank',
        display: 'bank',
        entry_type: 'word',
        match_kind: 'exact',
        matched_surface: 'bank',
      },
    ],
  })
  expect(screen.getByText('Available to generate')).toBeDefined()

  renderTool('generate_words', {
    items: [{ job_id: 'pending' }, { error: 'invalid_reference' }],
  })
  expect(screen.getByText(/invalid_reference/)).toBeDefined()

  renderTool('generate_words', {
    items: [
      { status: 'running' },
      {
        status: 'succeeded',
        senses: [
          {
            sense_id: 1,
            lemma: 'bank',
            pos: 'noun',
            definition: 'a financial institution',
          },
        ],
      },
    ],
  })
  expect(screen.getByText('a financial institution')).toBeDefined()
})
