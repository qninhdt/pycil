import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ClerkAPIResponseError } from '@clerk/backend/errors'
import { createClerkClient } from '@clerk/backend'
import { createServer } from 'node:http'
import { once } from 'node:events'
import {
  createSignInToken,
  deleteIdentityUser,
  identityFailure,
  isRateLimitError,
  provisionIdentity,
  withClerkRetry,
} from '../fixtures/users.ts'

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

test('isRateLimitError identifies HTTP 429 across Clerk errors, status objects, and aggregate errors', () => {
  const clerk429 = new ClerkAPIResponseError('rate limited', {
    status: 429,
    data: [{ code: 'rate_limit_exceeded', message: 'too many requests' }],
  })
  assert.equal(isRateLimitError(clerk429), true)

  const clerkCodeOnly = new ClerkAPIResponseError('rate limited', {
    status: 400,
    data: [{ code: 'rate_limit_exceeded', message: 'too many requests' }],
  })
  assert.equal(isRateLimitError(clerkCodeOnly), true)

  const statusObj = { status: 429 }
  assert.equal(isRateLimitError(statusObj), true)

  const wrappedError = new Error('Clerk identity request failed (HTTP 429; rate_limit_exceeded)')
  assert.equal(isRateLimitError(wrappedError), true)

  const aggError = new AggregateError([new Error('Other'), wrappedError])
  assert.equal(isRateLimitError(aggError), true)

  assert.equal(isRateLimitError(new Error('Other error')), false)
  assert.equal(isRateLimitError({ status: 500 }), false)
})

test('withClerkRetry retries on 429 with backoff and jitter, then succeeds', async () => {
  let attempts = 0
  const result = await withClerkRetry(async () => {
    attempts++
    if (attempts < 3) {
      throw new ClerkAPIResponseError('rate limited', {
        status: 429,
        data: [{ code: 'rate_limit_exceeded', message: 'too many requests' }],
      })
    }
    return 'success'
  }, { initialDelayMs: 5, maxDelayMs: 20, maxAttempts: 4 })

  assert.equal(attempts, 3)
  assert.equal(result, 'success')
})

test('withClerkRetry aborts immediately on non-429 error', async () => {
  let attempts = 0
  await assert.rejects(
    withClerkRetry(async () => {
      attempts++
      throw new ClerkAPIResponseError('forbidden', {
        status: 403,
        data: [{ code: 'not_allowed', message: 'forbidden' }],
      })
    }, { initialDelayMs: 5, maxAttempts: 3 }),
    /forbidden/
  )
  assert.equal(attempts, 1)
})

test('withClerkRetry respects maxAttempts when 429 persists', async () => {
  let attempts = 0
  await assert.rejects(
    withClerkRetry(async () => {
      attempts++
      throw new ClerkAPIResponseError('rate limited', {
        status: 429,
        data: [{ code: 'rate_limit_exceeded', message: 'too many requests' }],
      })
    }, { initialDelayMs: 5, maxDelayMs: 15, maxAttempts: 3 }),
    /rate limited/
  )
  assert.equal(attempts, 3)
})

test('createSignInToken retries on HTTP 429 and returns valid token', async () => {
  let calls = 0
  const server = createServer((request, response) => {
    assert.equal(request.method, 'POST')
    assert.equal(request.url, '/v1/sign_in_tokens')
    calls++
    response.setHeader('Content-Type', 'application/json')
    if (calls === 1) {
      response.writeHead(429).end(JSON.stringify({ errors: [{ code: 'rate_limit_exceeded', message: 'Rate limit' }] }))
    } else {
      response.end(JSON.stringify({ object: 'sign_in_token', id: 'sit_123', token: 'ticket_tok_xyz', user_id: 'user_123', status: 'pending' }))
    }
  })
  server.listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  assert.ok(address && typeof address !== 'string')
  const client = createClerkClient({ secretKey: 'sk_test_support_only', apiUrl: `http://127.0.0.1:${address.port}` })

  try {
    const token = await createSignInToken(client, 'user_123', 300, { initialDelayMs: 5, maxDelayMs: 20, maxAttempts: 3 })
    assert.equal(token.token, 'ticket_tok_xyz')
    assert.equal(calls, 2)
  } finally {
    server.closeAllConnections()
    await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve()))
  }
})
