import { runInNewContext } from 'node:vm'
import { expect,test } from 'vitest'
import { aiOpenKey,initialUiScript,navigationCollapsedKey } from '../../src/lib/ui-preferences'

function firstPaint(hour: number, saved: Record<string, string> = {}, blocked = false) {
  const classes = new Set<string>()
  const root = { dataset: {} as Record<string, string>, lang: 'en', classList: { add: (value: string) => classes.add(value) } }
  runInNewContext(initialUiScript, {
    document: { documentElement: root },
    Date: class { getHours() { return hour } },
    localStorage: { getItem(key: string) { if (blocked) throw new Error('blocked'); return saved[key] ?? null } },
  })
  return { ...root, classes }
}

test('first paint restores supported preferences before hydration', () => {
  const root = firstPaint(6, { 'bauhaus-theme': 'dark', 'pycil-locale': 'vi', [navigationCollapsedKey]: 'true', [aiOpenKey]: 'true' })
  expect(root.dataset).toEqual({ timeOfDay: 'morning', navigationCollapsed: 'true', aiOpen: 'true' })
  expect(root.lang).toBe('vi')
  expect(root.classes.has('dark')).toBe(true)
  expect(firstPaint(12, { 'pycil-locale': 'en' }).lang).toBe('en')
})

test('invalid preferences and unavailable storage use safe first-paint defaults', () => {
  const root = firstPaint(23, { 'pycil-locale': 'xx', 'bauhaus-theme': 'invented', [navigationCollapsedKey]: 'yes', [aiOpenKey]: 'yes' })
  expect(root.dataset).toEqual({ timeOfDay: 'night', navigationCollapsed: 'false', aiOpen: 'false' })
  expect(root.lang).toBe('en')
  expect(root.classes.size).toBe(0)
  expect(firstPaint(13, {}, true).dataset).toEqual({ timeOfDay: 'afternoon', navigationCollapsed: 'false', aiOpen: 'false' })
})
