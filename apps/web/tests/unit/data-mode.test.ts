import { expect,test } from 'vitest'

import { resolveDataMode } from '../../src/lib/services/config'

test('mode selection defaults to live and rejects misspelled configuration', () => {
  expect(resolveDataMode()).toBe('live')
  expect(resolveDataMode('live')).toBe('live')
  expect(resolveDataMode('mock')).toBe('mock')
  expect(() => resolveDataMode('mok')).toThrow()
})
