import type { ThreadMessage } from '@assistant-ui/react'
import { expect,test } from 'vitest'
import { mergeAssistantTurns } from '../../src/features/assistant/messages'

function message(id: string, role: 'assistant' | 'user', text: string, complete = true): ThreadMessage {
  const common = { id, createdAt: new Date('2026-10-12T00:00:00Z'), content: [{ type: 'text' as const, text }], metadata: { custom: {}, unstable_state: {}, unstable_annotations: [], unstable_data: [], steps: [] } }
  return role === 'user' ? { ...common, role, attachments: [], metadata: { custom: {} } } : { ...common, role, status: complete ? { type: 'complete', reason: 'stop' } : { type: 'running' } }
}

test('completed snapshots restore canonical content while a running message keeps its incremental content', () => {
  const saved = message('answer', 'assistant', 'reasoning and answer')
  expect(mergeAssistantTurns([message('answer', 'assistant', 'answer')], [saved])[0].content).toEqual(saved.content)
  const live = message('answer', 'assistant', 'incremental', false)
  expect(mergeAssistantTurns([live], [saved])[0].content).toEqual(live.content)
})

test('tool rounds merge adjacent assistant chunks and keep user boundaries and inputs intact', () => {
  const messages = [message('a', 'assistant', 'thinking', false), message('b', 'assistant', 'done'), message('u', 'user', 'next'), message('c', 'assistant', 'reply')]
  const before = structuredClone(messages)
  const merged = mergeAssistantTurns(messages)
  expect(merged.map(item => item.id)).toEqual(['a', 'u', 'c'])
  expect(merged[0].content).toEqual([...messages[0].content, ...messages[1].content])
  expect(merged[0].role === 'assistant' && merged[0].status.type).toBe('complete')
  expect(messages).toEqual(before)
  expect(mergeAssistantTurns([])).toEqual([])
})
