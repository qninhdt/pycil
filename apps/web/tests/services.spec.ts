import { test, expect } from '@playwright/test'
import { QueryClient } from '@tanstack/react-query'
import { createMockServices } from '../src/lib/services/mock'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { createHttpServices } from '../src/lib/services/http'
import { resolveDataMode } from '../src/lib/services/config'
import { reportingDay, shiftDay } from '../src/lib/home-calendar'

const now = () => new Date('2026-10-07T02:00:00Z')
const signal = () => new AbortController().signal

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
