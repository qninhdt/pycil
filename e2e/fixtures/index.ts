import { test as base, expect, type BrowserContext, type Page } from '@playwright/test'
import { createActor, deleteIdentity, type Actor } from './actors.ts'
import { Data, vocabulary, type Vocabulary } from './data.ts'
import { webURL } from '../support/environment.ts'
import { createScenarios } from './provider.ts'

async function installLocalhostCookieFix(context: BrowserContext) {
  await context.addInitScript(() => {
    const proto = Document.prototype
    const desc = Object.getOwnPropertyDescriptor(proto, 'cookie')
    if (desc && desc.set) {
      const orig = desc.set
      Object.defineProperty(document, 'cookie', {
        configurable: true,
        enumerable: true,
        get() { return desc.get ? desc.get.call(this) : '' },
        set(val) {
          if (typeof val === 'string' && (window.location.hostname === 'localhost' || !window.location.hostname.includes('.'))) {
            val = val.replace(/;\s*domain=\.?localhost/gi, '')
          }
          return orig.call(this, val)
        }
      })
    }
  })
}

function isIgnorableBrowserError(error: Error): boolean {
  // WebKit bug: DocumentThreadableLoader surfaces "<same-origin> due to access control checks"
  // when an in-flight fetch/prefetch is canceled by page navigation or document unload.
  const msg = error?.message || String(error)
  return (msg.includes('Fetch API cannot load') || msg.includes('access control checks')) && (msg.includes('localhost:3200') || msg.includes('_rsc'))
}

function browserErrors(context: BrowserContext) {
  const errors: Error[] = []
  const attach = (page: Page) => page.on('pageerror', error => {
    if (!isIgnorableBrowserError(error)) errors.push(error)
  })
  context.pages().forEach(attach)
  context.on('page', attach)
  return errors
}

export const test = base.extend<{ actor: Actor; secondary: Actor; guest: Page; data: Data; vocabulary: Vocabulary; scenarios: Awaited<ReturnType<typeof createScenarios>> }>({
  context: async ({ context }, provide) => {
    await installLocalhostCookieFix(context)
    const errors = browserErrors(context)
    await provide(context)
    expect(errors, 'Unexpected browser exceptions').toEqual([])
  },
  actor: async ({ page }, provide) => {
    const actor = await createActor(page)
    const errors: unknown[] = []
    try { await provide(actor) } catch (error) { errors.push(error) }
    const results = await Promise.allSettled([actor.api.dispose(), page.context().close()])
    errors.push(...results.filter(result => result.status === 'rejected').map(result => result.reason))
    try { await deleteIdentity(actor.subject) } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'Actor fixture failed')
  },
  secondary: async ({ browser, contextOptions }, provide) => {
    const context = await browser.newContext({ ...contextOptions, baseURL: webURL })
    await installLocalhostCookieFix(context)
    const exceptions = browserErrors(context)
    let actor: Actor | undefined
    const errors: unknown[] = []
    try {
      actor = await createActor(await context.newPage())
      await provide(actor)
    } catch (error) { errors.push(error) }
    const results = await Promise.allSettled([actor?.api.dispose(), context.close()])
    errors.push(...results.filter(result => result.status === 'rejected').map(result => result.reason))
    errors.push(...exceptions)
    if (actor) try { await deleteIdentity(actor.subject) } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'Secondary actor fixture failed')
  },
  guest: async ({ browser, contextOptions }, provide) => {
    const context = await browser.newContext({ ...contextOptions, baseURL: webURL, storageState: undefined })
    await installLocalhostCookieFix(context)
    const errors: unknown[] = browserErrors(context)
    try { await provide(await context.newPage()) } catch (error) { errors.push(error) }
    try { await context.close() } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'Guest fixture failed')
  },
  data: async ({ actor }, provide) => {
    const data = new Data(actor)
    try { await provide(data) } finally { await data.cleanup() }
  },
  // eslint-disable-next-line no-empty-pattern -- Playwright discovers fixture dependencies through destructuring.
  scenarios: async ({}, provide) => {
    const scenarios = await createScenarios()
    try { await provide(scenarios) } finally { await scenarios.cleanup() }
  },
  // eslint-disable-next-line no-empty-pattern -- Playwright discovers fixture dependencies through destructuring.
  vocabulary: async ({}, provide) => { await provide(await vocabulary()) },
})
export { expect }
