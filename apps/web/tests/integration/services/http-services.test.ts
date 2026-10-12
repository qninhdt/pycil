import { expect,test } from 'vitest'

import { ApiError,fetchProfile } from '../../../src/lib/api'

import { createMockServices } from '../../../src/lib/services/mock'

import { createHttpServices } from '../../../src/lib/services/http'

import { homeRequest,homeToken,parseSummary } from '../../../src/lib/home-api'

test('account adapter sends bearer tokens and distinguishes API failures', async () => {
  const original = globalThis.fetch
  let request: RequestInit | undefined
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/me'); request = init
    return new Response(JSON.stringify({ ...createMockServices().account.initialProfile, id: 'account-1', display_name: 'Learner' }))
  }
  try {
    expect((await fetchProfile('session-token')).display_name).toBe('Learner')
    expect(request?.headers).toEqual({ Authorization: 'Bearer session-token' })
    expect(request?.cache).toBe('no-store')
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'invalid_credentials' }), { status: 401 })
    await expect(fetchProfile('expired')).rejects.toMatchObject({ status: 401, code: 'invalid_credentials' })
    globalThis.fetch = async () => new Response(JSON.stringify({ id: 'account-1', plan: 'invented' }))
    await expect(fetchProfile('session-token')).rejects.toBeInstanceOf(ApiError)
  } finally { globalThis.fetch = original }
})

const signal = () => new AbortController().signal

test('usage adapter sends bearer authentication and parses the native allowance', async () => {
  const allowance = { period_start: '2026-10-01T00:00:00Z', period_end: '2026-11-01T00:00:00Z', allowance_units: 100, used_units: 120, remaining_units: 0 }
  const original = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/me/usage')
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer session')
    return Response.json(allowance)
  }
  try { expect(await createHttpServices(async () => 'session').account.usage(signal())).toEqual(allowance) }
  finally { globalThis.fetch = original }
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
    const grade = { question_artifact_id: 1, question_type: 'WORD_TO_DEFINITION' as const, format: 'SHORT_ANSWER' as const, answer: 'a bank' }
    const results = [{ question_artifact_id: 1, question_type: 'WORD_TO_DEFINITION' as const, format: 'SINGLE_CHOICE' as const, diagnostics: { correct: true }, answered_at: new Date().toISOString() }]
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
      { path: '/api/v1/study:submitResults', method: 'POST', body: { results } },
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
      { path: '/api/v1/nodes', method: 'POST', body: { type: 'REFERENCE', name: 'saved source', parent_id: 'personal', reference_id: 'source', confirm_publication: false } },
    ])
    expect(calls.every(call => call.authorization === 'Bearer session')).toBe(true)
    expect(calls.some(call => call.path.endsWith('/editor'))).toBe(false)
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

const now = () => new Date('2026-10-07T02:00:00Z')

test('live list adapter resolves reference types through readable endpoints, deduplicates targets and never guesses missing ones', async () => {
  const original = globalThis.fetch
  const requests: string[] = []
  const details = { id: 'source-folder', name: 'Readable folder', type: 'FOLDER', space: 'PUBLISHED', owner_id: 'owner', role: 'NORMAL', description: null,
    created_at: now().toISOString(), updated_at: now().toISOString(), breadcrumbs: [], reference_id: null, reference_available: null }
  const reference = (id: string, reference_id: string) => ({ id, name: id, type: 'REFERENCE', description: null, summary: null, reference_id })
  globalThis.fetch = async (url, init) => {
    requests.push(String(url))
    expect(init?.headers).toEqual({ Authorization: 'Bearer test-token' })
    if (String(url).startsWith('/api/v1/nodes?')) return new Response(JSON.stringify({ nodes: [reference('first', 'source-folder'), reference('second', 'source-folder'), reference('unavailable', 'hidden-source')], next_cursor: 'page-2' }))
    if (String(url) === '/api/v1/nodes/source-folder') return new Response(JSON.stringify(details))
    return new Response(JSON.stringify({ error: 'node_not_found' }), { status: 404 })
  }
  try {
    const result = await createHttpServices(async () => 'test-token').library.list('parent', signal())
    expect(result.nodes.map(node => node.target_type)).toEqual(['FOLDER', 'FOLDER', null])
    expect(result.nodes[2].reference_id).toBeNull()
    expect(result.next_cursor).toBe('page-2')
    expect(requests.filter(path => path === '/api/v1/nodes/source-folder')).toHaveLength(1)
    expect(requests).toHaveLength(3)
  } finally { globalThis.fetch = original }
})

const summary = { node_id: 'library-root', as_of: '2026-10-07T02:00:00Z', total: 142, new: 46, studied: 96, due: 12, not_due: 84, last_studied_at: '2026-10-06T02:00:00Z', reachable_decks: 4 }

test('Home requests use bearer authentication and tokens can be cancelled while loading', async () => {
  const original = globalThis.fetch
  let init: RequestInit | undefined
  globalThis.fetch = async (_url, options) => { init = options; return new Response(JSON.stringify(summary)) }
  try {
    expect((await homeRequest('study/progress', 'bearer', parseSummary, new AbortController().signal)).due).toBe(12)
    expect(init?.cache).toBe('no-store')
    expect(init?.headers).toEqual({ Authorization: 'Bearer bearer' })
    const controller = new AbortController()
    const waiting = homeToken(() => new Promise(() => {}), controller.signal)
    controller.abort(new Error('timed out'))
    await expect(waiting).rejects.toThrow('timed out')
    await expect(homeToken(async () => null, new AbortController().signal)).rejects.toMatchObject({ status: 401 })
  } finally { globalThis.fetch = original }
})

test('live adapter sends a membership delta without reading or replacing a deck', async () => {
  const original = globalThis.fetch
  const requests: { path: string; method: string; body: unknown }[] = []
  globalThis.fetch = async (url, init) => {
    requests.push({ path: String(url), method: init?.method ?? 'GET', body: JSON.parse(String(init?.body)) })
    return new Response(JSON.stringify({ total: 1 }))
  }
  try {
    await createHttpServices(async () => 'test-token').library.updateDeckSenses('deck', { add: [49], remove: [50] }, signal())
    expect(requests).toEqual([{ path: '/api/v1/nodes/deck:modifySenses', method: 'POST', body: { add: [49], remove: [50] } }])
  } finally { globalThis.fetch = original }
})

test('anonymous published contents omit bearer and private summary while preserving search and cursor', async () => {
  const original = globalThis.fetch
  let tokenCalls = 0
  const calls: { url: URL; headers: Headers }[] = []
  globalThis.fetch = async (input, init) => {
    calls.push({ url: new URL(String(input), 'http://localhost'), headers: new Headers(init?.headers) })
    return Response.json({ nodes: [], next_cursor: null })
  }
  try {
    const services = createHttpServices(async () => { tokenCalls++; return 'private-token' })
    expect(await services.library.contents('published', { q: 'bank', cursor: 'next', limit: 5 }, signal(), true)).toEqual({ nodes: [], next_cursor: null })
    expect(tokenCalls).toBe(0)
    expect(calls[0].headers.has('Authorization')).toBe(false)
    expect(calls[0].url.searchParams.get('include')).toBeNull()
    expect(calls[0].url.searchParams.get('cursor')).toBe('next')
    expect(calls[0].url.searchParams.get('q')).toBe('bank')
    expect(calls[0].url.pathname).toBe('/api/v1/nodes/published:search')
    expect(calls[0].url.searchParams.get('limit')).toBe('5')
  } finally { globalThis.fetch = original }
})
