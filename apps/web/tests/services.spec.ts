import { test, expect } from '@playwright/test'
import { QueryClient } from '@tanstack/react-query'
import { createMockServices } from '../src/lib/services/mock'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { createHttpServices } from '../src/lib/services/http'
import { resolveDataMode } from '../src/lib/services/config'
import { reportingDay, shiftDay } from '../src/lib/home-calendar'
import { parseUsageAllowance } from '../src/lib/api'
import { createAssistantService, AssistantError } from '../src/lib/assistant-api'

const now = () => new Date('2026-10-07T02:00:00Z')
const signal = () => new AbortController().signal

test('conversation deletion sends authenticated DELETE, handles 204 and preserves backend errors', async () => {
  const original = globalThis.fetch
  let denied = false
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/assistant/conversations/owned-id')
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

test('AI allowance uses backend units, including overspend, and rejects inconsistent data', async () => {
  const allowance = { period_start: '2026-10-01T00:00:00Z', period_end: '2026-11-01T00:00:00Z', allowance_units: 100, used_units: 120, remaining_units: 0 }
  expect(parseUsageAllowance(allowance)).toEqual(allowance)
  expect(() => parseUsageAllowance({ ...allowance, remaining_units: 1 })).toThrow()
  expect(() => parseUsageAllowance({ ...allowance, used_units: -1 })).toThrow()
  expect(() => parseUsageAllowance({ ...allowance, period_end: allowance.period_start })).toThrow()
  const original = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/me/usage')
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session')
    return Response.json(allowance)
  }
  try { expect(await createHttpServices(async () => 'session').account.usage(signal())).toEqual(allowance) }
  finally { globalThis.fetch = original }
})

test('mode selection defaults to live and rejects misspelled configuration', () => {
  expect(resolveDataMode()).toBe('live')
  expect(resolveDataMode('live')).toBe('live')
  expect(resolveDataMode('mock')).toBe('mock')
  expect(() => resolveDataMode('mok')).toThrow()
})

test('JSON adapter implements the shared contract entirely offline and protects the seed', async () => {
  const original = globalThis.fetch
  let calls = 0
  globalThis.fetch = async () => { calls++; throw new Error('Mock mode must never fetch') }
  try {
    const service = createMockServices({ now, latency: 0 })
    const profile = await service.account.profile(signal())
    const summary = await service.learning.summary(undefined, signal())
    expect(profile.display_name).toBe(database.account.display_name)
    expect(summary).toMatchObject(database.summary)
    const today = reportingDay(now(), profile.settings!.timezone)
    const activity = await service.learning.activity({ start: shiftDay(today, -6), end: today }, signal())
    expect(activity.days).toHaveLength(7)
    expect(activity.current_streak).toBe(6)
    expect(activity.applied_events + activity.practice_events).toBe(activity.days.reduce((sum, day) => sum + day.applied_events + day.practice_events, 0))
    const schedule = await service.learning.schedule({ start: today, end: shiftDay(today, 6) }, signal())
    expect(schedule.days.map(day => day.count)).toEqual(database.schedule.map(day => day.count))
    const library = await service.library.list(profile.personal_node_id, signal())
    expect(library.nodes).toHaveLength(4)
    expect(library.nodes.find(node => node.id === 'saved-business')).toMatchObject({ type: 'REFERENCE', target_type: 'FOLDER' })
    expect((await service.learning.prepare({ node_id: profile.library_node_id, selection: 'DUE' }, signal())).actual_sense_count).toBe(10)
    profile.display_name = 'Mutated'
    library.nodes[0].name = 'Mutated'
    expect((await service.account.profile(signal())).display_name).toBe('Alex')
    expect((await service.library.list(profile.personal_node_id, signal())).nodes[0].name).toBe('Everyday conversation')
    expect(calls).toBe(0)
  } finally { globalThis.fetch = original }
})

test('mock cancellation, invalid scopes and selection modes behave like a service, not component constants', async () => {
  const service = createMockServices({ now, latency: 100 })
  const controller = new AbortController()
  const pending = service.learning.summary(undefined, controller.signal)
  controller.abort(new Error('Cancelled'))
  await expect(pending).rejects.toThrow('Cancelled')
  await expect(service.learning.summary('not-a-node', signal())).rejects.toMatchObject({ status: 404 })
  const db = structuredClone(database)
  db.summary.due = 0; db.summary.not_due = db.summary.studied; db.library.due_sense_ids = []
  const noDue = createMockServices({ database: db, now, latency: 0 })
  expect((await noDue.learning.prepare({ node_id: db.account.library_node_id, selection: 'DUE' }, signal())).actual_sense_count).toBe(0)
  expect((await noDue.learning.prepare({ node_id: db.account.library_node_id, selection: 'NEW', max_sense_count: 3 }, signal())).actual_sense_count).toBe(3)
})

test('live adapter uses real bearer HTTP requests with no fallback to mock data', async () => {
  const original = globalThis.fetch
  const requests: { url: string; init?: RequestInit }[] = []
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init })
    return new Response(JSON.stringify({ error: 'not_ready' }), { status: 503 })
  }
  try {
    const live = createHttpServices(async () => 'real-session-token')
    await expect(live.learning.summary(undefined, signal())).rejects.toMatchObject({ status: 503 })
    expect(requests[0].url).toBe('/api/v1/study/progress')
    expect(requests[0].init?.headers).toEqual({ Authorization: 'Bearer real-session-token' })
    expect(requests[0].init?.cache).toBe('no-store')
    const anonymous = createHttpServices(async () => null)
    await expect(anonymous.learning.summary(undefined, signal())).rejects.toMatchObject({ status: 401 })
    expect(requests).toHaveLength(1)
  } finally { globalThis.fetch = original }
})

test('query keys isolate mock/live and user scopes even for the same resource', async () => {
  const queryClient = new QueryClient()
  try {
    queryClient.setQueryData(['mock', 'alex', 'progress'], { due: 12 })
    expect(queryClient.getQueryData(['live', 'alex', 'progress'])).toBeUndefined()
    expect(queryClient.getQueryData(['mock', 'other-user', 'progress'])).toBeUndefined()
    await queryClient.cancelQueries()
    queryClient.clear()
    expect(queryClient.getQueryData(['mock', 'alex', 'progress'])).toBeUndefined()
  } finally { queryClient.clear() }
})

test('live action requests preserve payloads, review keys and bearer authentication', async () => {
  const original = globalThis.fetch
  const calls: { path: string; method: string; headers: Headers; body: unknown }[] = []
  globalThis.fetch = async (url, init) => {
    calls.push({ path: String(url), method: init?.method ?? 'GET', headers: new Headers(init?.headers), body: init?.body ? JSON.parse(String(init.body)) : null })
    return Response.json({ error: 'not_ready' }, { status: 503 })
  }
  try {
    const service = createHttpServices(async () => 'session')
    const prepare = { node_id: 'deck', selection: 'NEW' as const, max_sense_count: 3 }
    const grade = { question_id: 1, format: 'SHORT_ANSWER' as const, answer: 'a bank' }
    const results = [{ sense_id: 1, rating: 'GOOD' as const }]
    await expect(service.learning.prepare(prepare, signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.learning.grade(grade, signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.learning.review({ results, key: 'stable-review-key' }, signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.dictionary.search('bank & river', signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.dictionary.previews([1, 2], signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.account.publicProfile('a+b', signal())).rejects.toMatchObject({ status: 503 })
    await expect(service.library.contents('folder', { q: 'bank & river' }, signal())).rejects.toMatchObject({ status: 503 })
    expect(calls.slice(0, 3).map(({ path, method, body }) => ({ path, method, body }))).toEqual([
      { path: '/api/v1/study:prepare', method: 'POST', body: prepare },
      { path: '/api/v1/study:grade', method: 'POST', body: grade },
      { path: '/api/v1/study:submitReviews', method: 'POST', body: { results } },
    ])
    expect(calls[2].headers.get('Idempotency-Key')).toBe('stable-review-key')
    expect(new URL(calls[3].path, 'https://test.invalid').pathname).toBe('/api/v1/words:search')
    expect(new URL(calls[3].path, 'https://test.invalid').searchParams.get('query')).toBe('bank & river')
    expect(calls[4]).toMatchObject({ path: '/api/v1/words:batchPreview', method: 'POST', body: { word_ids: [1, 2] } })
    expect(calls[5].path).toBe('/api/v1/users:lookup?handle=a%2Bb')
    expect(new URL(calls[6].path, 'https://test.invalid').pathname).toBe('/api/v1/nodes/folder:search')
    expect(new URL(calls[6].path, 'https://test.invalid').searchParams.get('q')).toBe('bank & river')
    expect(calls.filter((_, index) => index < 3 || index === 6).every(call => call.headers.get('Authorization') === 'Bearer session')).toBe(true)
    expect(calls.slice(3, 6).every(call => call.headers.get('Authorization') === null)).toBe(true)
  } finally { globalThis.fetch = original }
})

test('live Library writes use targeted contracts and explicit publication consent', async () => {
  const original = globalThis.fetch
  const calls: { path: string; method: string; body: unknown; authorization: string | null }[] = []
  globalThis.fetch = async (url, init) => {
    calls.push({ path: String(url), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null, authorization: new Headers(init?.headers).get('Authorization') })
    return Response.json({ id: 'saved-node' })
  }
  try {
    const service = createHttpServices(async () => 'session')
    await service.library.updateNode('deck', { name: 'renamed', description: null }, signal())
    await service.library.updateDeckSenses('deck', { add: [3], remove: [1] }, signal())
    await service.library.moveNode('deck', 'published', signal(), { confirm: true, retainReference: true })
    expect(await service.library.copyNode('deck', 'folder', signal())).toBe('saved-node')
    expect(await service.library.createReference('personal', 'source', 'saved source', signal())).toBe('saved-node')
    expect(calls.map(({ path, method, body }) => ({ path, method, body }))).toEqual([
      { path: '/api/v1/nodes/deck', method: 'PATCH', body: { name: 'renamed', description: null } },
      { path: '/api/v1/nodes/deck:modifySenses', method: 'POST', body: { add: [3], remove: [1] } },
      { path: '/api/v1/nodes/deck:move', method: 'POST', body: { parent_id: 'published', confirm_publication: true, retain_personal_reference: true } },
      { path: '/api/v1/nodes/deck:copy', method: 'POST', body: { parent_id: 'folder', confirm_publication: false } },
      { path: '/api/v1/nodes', method: 'POST', body: { type: 'REFERENCE', name: 'saved source', parent_id: 'personal', reference_id: 'source' } },
    ])
    expect(calls.every(call => call.authorization === 'Bearer session')).toBe(true)
    expect(calls.some(call => call.path.endsWith('/editor'))).toBe(false)
  } finally { globalThis.fetch = original }
})

test('live Assistant action returns the native SSE response', async () => {
  const original = globalThis.fetch
  const stream = new Response('data: {"type":"RUN_FINISHED"}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
  const controller = new AbortController()
  const input = { threadId: 'conversation', runId: 'run', messages: [], state: {}, tools: [], context: [] }
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/assistant:run')
    expect(init).toMatchObject({ method: 'POST', signal: controller.signal, body: JSON.stringify(input) })
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session')
    expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream')
    return stream
  }
  try {
    expect(await createHttpServices(async () => 'session').assistant!.run(input, controller.signal)).toBe(stream)
  } finally { globalThis.fetch = original }
})

test('Discovery is public and source pages preserve canonical owner routes', async () => {
  const original = globalThis.fetch
  const calls: { path: string; authorization: string | null }[] = []
  globalThis.fetch = async (url, init) => {
    calls.push({ path: String(url), authorization: new Headers(init?.headers).get('Authorization') })
    return Response.json(String(url).includes('discovery') ? { nodes: [], next_cursor: null } : { decks: [{ id: 'deck', name: 'Shared', owner_id: 'author', space: 'PUBLISHED', editable: false }], next_cursor: 'opaque-next' })
  }
  try {
    const service = createHttpServices(async () => 'session')
    await service.library.discovery({ q: 'work & life', type: 'DECK', cursor: 'opaque+cursor' }, signal())
    const query = new URL(calls[0].path, 'https://test.invalid').searchParams
    expect(query.get('q')).toBe('work & life')
    expect(query.get('cursor')).toBe('opaque+cursor')
    expect(calls[0].authorization).toBeNull()
    expect(await service.library.sources('scope', 1, undefined, signal())).toEqual({ decks: [{ id: 'deck', name: 'Shared', owner_id: 'author', space: 'PUBLISHED' }], next_cursor: 'opaque-next' })
    expect(calls[1].authorization).toBe('Bearer session')
  } finally { globalThis.fetch = original }
})

test('preview Discovery, references and publication use the shared Library state', async () => {
  const service = createMockServices({ latency: 0 })
  const profile = await service.account.profile(signal())
  const id = await service.library.createDeck(profile.personal_node_id, 'Publish this', [1], signal())
  await expect(service.library.moveNode(id, profile.published_node_id, signal())).rejects.toMatchObject({ status: 409 })
  await service.library.moveNode(id, profile.published_node_id, signal(), { confirm: true, retainReference: true })
  expect((await service.library.discovery({ q: 'Publish this' }, signal())).nodes.map(node => node.id)).toContain(id)
  const reference = await service.library.createReference(profile.personal_node_id, id, 'Saved', signal())
  expect((await service.library.details(reference, signal())).target?.id).toBe(id)
  expect((await service.library.meanings(reference, {}, signal())).senses.map(sense => sense.sense_id)).toEqual([1])
  expect((await service.library.sources(reference, 1, undefined, signal())).decks.map(deck => deck.id)).toEqual([id])
  await expect(service.library.sources(reference, 2, undefined, signal())).rejects.toMatchObject({ status: 404 })
})
