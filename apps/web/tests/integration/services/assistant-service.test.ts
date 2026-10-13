import { expect,test } from 'vitest'

import { createHttpServices } from '../../../src/lib/services/http'

import { getApiBaseUrl } from '../../../src/lib/services/config'
import { AssistantError,createAssistantService } from '../../../src/lib/assistant-api'

const apiBase = getApiBaseUrl()
const signal = () => new AbortController().signal

test('conversation deletion sends authenticated DELETE, handles 204 and preserves backend errors', async () => {
  const original = globalThis.fetch
  let denied = false
  globalThis.fetch = async (url, init) => {
    expect(url).toBe(`${apiBase}/assistant/conversations/owned-id`)
    expect(init?.method).toBe('DELETE')
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session')
    return denied ? Response.json({ error: 'conversation_busy' }, { status: 409 }) : new Response(null, { status: 204 })
  }
  try {
    const service = createAssistantService(async () => 'session')
    await expect(service.remove('owned-id', signal())).resolves.toBeUndefined()
    denied = true
    await expect(service.remove('owned-id', signal())).rejects.toMatchObject({ status: 409, code: 'conversation_busy' })
    expect(new AssistantError(403, 'allowance_exhausted').message).toContain('reset date')
  } finally { globalThis.fetch = original }
})

test('live Assistant action returns the native SSE response', async () => {
  const original = globalThis.fetch
  const stream = new Response('data: {"type":"RUN_FINISHED"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  const controller = new AbortController()
  const input = { threadId: 'conversation', runId: 'run', messages: [], state: {}, tools: [], context: [] }
  globalThis.fetch = async (url, init) => {
    expect(url).toBe(`${apiBase}/assistant:run`)
    expect(init).toMatchObject({ method: 'POST', signal: controller.signal, body: JSON.stringify(input) })
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session')
    expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream')
    return stream
  }
  try {
    expect(await createHttpServices(async () => 'session').assistant!.run(input, controller.signal)).toBe(stream)
  } finally { globalThis.fetch = original }
})
