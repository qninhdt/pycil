import { expect, test } from 'vitest'
import { resolveLocale } from '../../src/lib/preferences/locale'
import { resolveTheme } from '../../src/lib/preferences/theme'

test('supported cookies win; invalid preferences fall back to supported request languages', () => {
  expect(resolveLocale('vi', 'en-US')).toBe('vi')
  expect(resolveLocale('invalid', 'fr-FR,vi-VN;q=0.9,en;q=0.7')).toBe('vi')
  expect(resolveLocale(undefined, 'vi;q=0,en;q=0.8')).toBe('en')
  expect(resolveLocale(undefined, 'en;q=0.1,vi;q=0.9')).toBe('vi')
  expect(resolveLocale(undefined, 'fr;q=1,vi;q=invalid')).toBe('en')
  expect(resolveLocale(undefined, null)).toBe('en')
  expect(resolveTheme('dark')).toBe('dark')
  expect(resolveTheme('unknown')).toBe('light')
  expect(resolveTheme(undefined)).toBe('light')
})
