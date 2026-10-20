import assert from 'node:assert/strict'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { test } from 'node:test'
import { requireFreePort } from './stack.ts'

test('an occupied port fails instead of reusing or selecting another port', async () => {
  const server = createServer().listen(0, '127.0.0.1')
  await once(server, 'listening')
  const address = server.address()
  assert(address && typeof address !== 'string')
  try { await assert.rejects(requireFreePort(address.port), /occupied/) }
  finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())) }
  await requireFreePort(address.port)
})
