import assert from 'node:assert/strict'
import { test } from 'node:test'
import { once } from 'node:events'
import { modelProvider } from './model-provider.ts'

test('isolates scenarios, rejects unmatched/exhausted calls, preserves native response', async () => {
  const server = modelProvider().listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  assert(address && typeof address !== 'string')
  const url = `http://127.0.0.1:${address.port}`
  const post = (path: string, value: unknown) => fetch(url + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(value) })
  try {
    for (const name of ['reserved-alpha', 'reserved-bravo']) {
      assert.equal((await post('/scenarios', { id: name, path: '/decisions', contains: name, responses: [{ status: 200, body: { answers: [{ type: 'answer', value: name }] } }] })).status, 201)
    }
    const results = await Promise.all(['reserved-bravo', 'reserved-alpha'].map(name => post('/decisions', { state: name })))
    assert.deepEqual(await results[0].json(), { answers: [{ type: 'answer', value: 'reserved-bravo' }] })
    assert.deepEqual(await results[1].json(), { answers: [{ type: 'answer', value: 'reserved-alpha' }] })
    assert.equal((await post('/decisions', { state: 'reserved-alpha' })).status, 500)
    assert.equal((await post('/decisions', { state: 'unknown' })).status, 500)
    assert.equal((await post('/scenarios', { id: 'invalid', responses: [] })).status, 400)
    assert.deepEqual(await (await fetch(url + '/scenarios/reserved-bravo')).json(), { consumed: 1, expected: 1, active: 0 })
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})

test('a stream gate exposes partial content, refuses deletion and releases completion explicitly', async () => {
  const server = modelProvider().listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  assert(address && typeof address !== 'string')
  const url = `http://127.0.0.1:${address.port}`
  const post = (path: string, value?: unknown) => fetch(url + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(value ?? {}) })
  try {
    assert.equal((await post('/scenarios', { id: 'stream-contract-check', path: '/chat/completions', contains: 'stream-contract-check', responses: [{ status: 200, chunks: [{ delta: 'first' }, { delta: 'last' }], pauseAfter: 1, requiredInput: ['expected-context'] }] })).status, 201)
    const response = await post('/chat/completions', { prompt: 'stream-contract-check expected-context' })
    const reader = response.body!.getReader()
    const first = await reader.read()
    assert.match(new TextDecoder().decode(first.value), /first/)
    assert.deepEqual(await (await fetch(url + '/scenarios/stream-contract-check')).json(), { consumed: 1, expected: 1, active: 1 })
    assert.equal((await fetch(url + '/scenarios/stream-contract-check', { method: 'DELETE' })).status, 409)
    assert.equal((await post('/scenarios/stream-contract-check/release')).status, 200)
    let remaining = ''
    for (;;) {
      const chunk = await reader.read()
      if (chunk.done) break
      remaining += new TextDecoder().decode(chunk.value)
    }
    assert.match(remaining, /last/)
    assert.match(remaining, /\[DONE\]/)
    assert.equal((await fetch(url + '/scenarios/stream-contract-check', { method: 'DELETE' })).status, 200)
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})

test('a held structured response keeps the request pending until fixture release', async () => {
  const server = modelProvider().listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  assert(address && typeof address !== 'string')
  const url = `http://127.0.0.1:${address.port}`
  const post = (path: string, value: unknown) => fetch(url + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(value) })
  try {
    await post('/scenarios', { id: 'held-structured-contract', path: '/chat/completions', contains: 'quay', responses: [{ status: 200, hold: true, body: { choices: [] } }] })
    const pending = post('/chat/completions', { target: 'quay' })
    // Receiving the first control request proves the model request was accepted.
    let active = 0
    for (let attempt = 0; attempt < 100 && !active; attempt++) active = (await (await fetch(url + '/scenarios/held-structured-contract')).json() as { active: number }).active
    assert.equal(active, 1)
    assert.equal((await post('/scenarios/held-structured-contract/release', {})).status, 200)
    assert.deepEqual(await (await pending).json(), { choices: [] })
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})
