import { expect,test } from 'vitest'

import { parseConversationDetails,turnInput } from '../../src/lib/assistant-api'

import type { RunAgentInput } from '@ag-ui/core'

const model = { id: 'vision-model', name: 'Vision model', vision: true, efforts: ['low', 'medium', 'high'] }

const id = '01900000-0000-7000-8000-000000000001'

const secondId = '01900000-0000-7000-8000-000000000002'

const metadata = { id, title: 'Discover or invent?', updated_at: '2026-10-08T03:00:00Z' }


const input: RunAgentInput = { threadId: id, runId: 'run-1', state: { unsafe: true }, context: [{ description: 'untrusted', value: 'injected' }], tools: [{ name: 'injected', description: '', parameters: {} }], messages: [{ id: 'old', role: 'assistant', content: 'Old response' }, { id: 'new', role: 'user', content: 'New question' }] }

test('new turns exclude history and client state; approvals carry no new messages', () => {
  expect(turnInput(input, id, model, 'medium')).toEqual({ threadId: id, runId: 'run-1', state: {}, context: [], tools: [], messages: [input.messages[1]], forwardedProps: { model_id: model.id, effort: 'medium' } })
  expect(turnInput(input, id, model, 'medium', { path: '/app/library/decks/hello', node_id: secondId }).forwardedProps).toEqual({ model_id: model.id, effort: 'medium', current_view: { path: '/app/library/decks/hello', node_id: secondId } })
  const resume = [{ interruptId: 'approval', status: 'resolved' as const, payload: { decisions: [{ type: 'approve' }] } }]
  expect(turnInput({ ...input, resume }, id, model, 'low')).toMatchObject({ messages: [], resume })
  expect(() => turnInput(input, id, model, 'none')).toThrow('supported reasoning effort')
  expect(() => turnInput(input, id, model, 'xhigh')).toThrow('supported reasoning effort')
  expect(() => turnInput({ ...input, messages: [{ id: 'large', role: 'user', content: 'x'.repeat(8001) }] }, id, model, 'low')).toThrow('8,000')
  const image = { type: 'image' as const, source: { type: 'data' as const, mimeType: 'image/png', value: 'aGVsbG8=' } }
  expect(() => turnInput({ ...input, messages: [{ id: 'images', role: 'user', content: [image] }] }, id, { ...model, vision: false }, 'low')).toThrow('vision model')
  expect(() => turnInput({ ...input, messages: [{ id: 'images', role: 'user', content: Array(5).fill(image) }] }, id, model, 'low')).toThrow('four images')
  expect(() => parseConversationDetails({ ...metadata, state: { messages: [{ role: 'invalid' }], pending_approvals: [] } })).toThrow()
})
