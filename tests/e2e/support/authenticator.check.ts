import assert from 'node:assert/strict'
import { test } from 'node:test'
import { authenticatorCode } from './authenticator.ts'

test('authenticator codes match RFC 6238 SHA-1 vectors and reject invalid secrets', () => {
  const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
  for (const [seconds, code] of [[59, '287082'], [1111111109, '081804'], [1111111111, '050471'], [1234567890, '005924'], [2000000000, '279037'], [20000000000, '353130']] as const) {
    assert.equal(authenticatorCode(secret, seconds * 1000), code)
  }
  assert.throws(() => authenticatorCode('!'), /invalid Base32/)
  assert.throws(() => authenticatorCode(''), /empty or incomplete/)
})
