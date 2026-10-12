import type { Browser,BrowserContext,Page } from '@playwright/test'
import { EventEmitter } from 'node:events'
import { expect,test } from 'vitest'
import { trackBrowserErrors } from '../e2e/helpers/browser-errors'

function context() {
  const page = new EventEmitter() as EventEmitter & Page
  return { page, value: Object.assign(new EventEmitter(), { pages: () => [page] }) as unknown as BrowserContext & EventEmitter }
}

test('guard catches failures on supplied, independent and later-created pages and restores listeners', async () => {
  const first = context(), second = context()
  const original = async () => second.value
  const browser = { newContext: original } as unknown as Browser
  const guard = trackBrowserErrors(browser, first.value)
  first.page.emit('pageerror', new Error('first context'))
  await browser.newContext()
  second.page.emit('pageerror', new Error('independent context'))
  const later = new EventEmitter() as EventEmitter & Page
  second.value.emit('page', later)
  later.emit('pageerror', new Error('new page'))
  later.emit('console', { type: () => 'error', text: () => 'console failure' })
  later.emit('console', { type: () => 'info', text: () => 'ordinary log' })
  expect(guard.errors).toHaveLength(3)
  expect(guard.errors.join('\n')).toContain('independent context')
  expect(guard.consoleErrors).toEqual(['console failure'])
  guard.dispose()
  expect(browser.newContext).toBe(original)
  for (const page of [first.page, second.page, later]) expect(page.listenerCount('pageerror')).toBe(0)
  expect(second.value.listenerCount('page')).toBe(0)
})
