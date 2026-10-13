import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ClerkAPIResponseError } from '@clerk/backend/errors'
import { createClerkClient } from '@clerk/backend'
import { createServer } from 'node:http'
import { once } from 'node:events'
import { deleteIdentityUser, identityFailure, provisionIdentity } from '../fixtures/actors.ts'

test('identity failures retain HTTP status and codes without leaking provider messages or metadata', () => {
  const error = new ClerkAPIResponseError('private provider message', {
    status: 429,
    data: [{ code: 'rate_limit_exceeded', message: 'private provider message', meta: { data: { token: 'private-token' } } }],
  })
  const failure = identityFailure(error)
  assert.ok(failure instanceof Error)
  assert.equal(failure.message, 'Clerk identity request failed (HTTP 429; rate_limit_exceeded)')
  const browserError = new Error('Browser failed')
  assert.equal(identityFailure(browserError), browserError)
})

for (const behavior of ['committed', 'not_committed', 'rejected', 'retry_failed'] as const) {
  test(`identity creation (${behavior}) preserves uniqueness and the one-retry limit`, async () => {
    const email = 'isolated+clerk_test@example.com'
    const user = { object: 'user', id: 'user_reserved', email_addresses: [{ id: 'email_reserved', email_address: email, linked_to: [] }] }
    let creates = 0
    let lookups = 0
    const server = createServer((request, response) => {
      const url = new URL(request.url!, 'http://localhost')
      response.setHeader('Content-Type', 'application/json')
      if (request.method === 'POST') {
        creates++
        if (behavior === 'rejected') {
          response.writeHead(400).end(JSON.stringify({ errors: [{ code: 'form_password_invalid', message: 'Invalid password' }] }))
        } else if (creates === 1 || behavior === 'retry_failed') request.socket.destroy()
        else response.end(JSON.stringify(user))
      } else {
        assert.equal(url.searchParams.get('email_address'), email)
        const data = behavior === 'committed' ? [user] : []
        if (url.pathname.endsWith('/count')) response.end(JSON.stringify({ object: 'total_count', total_count: data.length }))
        else {
          lookups++
          response.end(JSON.stringify(data))
        }
      }
    })
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    assert.ok(address && typeof address !== 'string')
    const client = createClerkClient({ secretKey: 'sk_test_support_only', apiUrl: `http://127.0.0.1:${address.port}` })
    try {
      if (behavior === 'rejected') {
        await assert.rejects(provisionIdentity(client, email, 'Password!7'), error => error instanceof ClerkAPIResponseError && error.status === 400)
        assert.equal(creates, 1)
        assert.equal(lookups, 0)
      } else if (behavior === 'retry_failed') {
        await assert.rejects(provisionIdentity(client, email, 'Password!7'), error => error instanceof ClerkAPIResponseError && error.errors.some(item => item.code === 'unexpected_error'))
        assert.equal(creates, 2)
        assert.equal(lookups, 1)
      } else {
        assert.equal((await provisionIdentity(client, email, 'Password!7')).id, user.id)
        assert.equal(creates, behavior === 'committed' ? 1 : 2)
        assert.equal(lookups, 1)
      }
    } finally {
      server.closeAllConnections()
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
    }
  })
}

for (const behavior of ['deleted', 'already_deleted', 'lost_committed_response', 'rejected', 'retry_failed'] as const) {
  test(`identity deletion (${behavior}) treats 404 as complete and bounds transport retries`, async () => {
    let deletes = 0
    const server = createServer((request, response) => {
      assert.equal(request.method, 'DELETE')
      assert.equal(request.url, '/v1/users/user_owned')
      deletes++
      response.setHeader('Content-Type', 'application/json')
      if (behavior === 'rejected') response.writeHead(403).end(JSON.stringify({ errors: [{ code: 'not_allowed', message: 'Forbidden' }] }))
      else if (behavior === 'retry_failed' || behavior === 'lost_committed_response' && deletes === 1) request.socket.destroy()
      else if (behavior === 'already_deleted' || behavior === 'lost_committed_response') response.writeHead(404).end(JSON.stringify({ errors: [{ code: 'resource_not_found', message: 'Already deleted' }] }))
      else response.end(JSON.stringify({ object: 'user', id: 'user_owned', deleted: true }))
    })
    server.listen(0, '127.0.0.1')
    await once(server, 'listening')
    const address = server.address()
    assert.ok(address && typeof address !== 'string')
    const client = createClerkClient({ secretKey: 'sk_test_support_only', apiUrl: `http://127.0.0.1:${address.port}` })
    try {
      if (behavior === 'rejected') await assert.rejects(deleteIdentityUser(client, 'user_owned'), /HTTP 403/)
      else if (behavior === 'retry_failed') await assert.rejects(deleteIdentityUser(client, 'user_owned'), /unexpected_error/)
      else await deleteIdentityUser(client, 'user_owned')
      assert.equal(deletes, ['lost_committed_response', 'retry_failed'].includes(behavior) ? 2 : 1)
    } finally {
      server.closeAllConnections()
      await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
    }
  })
}
