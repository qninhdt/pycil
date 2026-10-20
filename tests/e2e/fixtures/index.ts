import { test as base, expect, type BrowserContext, type Page } from '@playwright/test'
import {
  createUser,
  createWorkerUser,
  createSharedUserContext,
  deleteIdentity,
  installLocalhostCookieFix,
  type User,
  type WorkerCachedUser,
} from './users.ts'
import { Data, vocabulary, type Vocabulary } from './data.ts'
import { webURL } from '../support/environment.ts'
import { createScenarios } from './provider.ts'
import { Api } from '../support/api.ts'

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

export type TestFixtures = {
  user: User
  sharedUser: User
  secondary: User
  guest: Page
  data: Data
  sharedData: Data
  vocabulary: Vocabulary
  scenarios: Awaited<ReturnType<typeof createScenarios>>
}

export type WorkerFixtures = {
  workerSharedUser: WorkerCachedUser
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  workerSharedUser: [async ({ browser }, provide, workerInfo) => {
    const workerUser = await createWorkerUser(browser, workerInfo.workerIndex)
    try {
      await provide(workerUser)
    } finally {
      await workerUser.dispose()
    }
  }, { scope: 'worker' }],

  context: async ({ context }, provide) => {
    await installLocalhostCookieFix(context)
    const errors = browserErrors(context)
    await provide(context)
    expect(errors, 'Unexpected browser exceptions').toEqual([])
  },
  user: async ({ page }, provide) => {
    const user = await createUser(page)
    const errors: unknown[] = []
    try { await provide(user) } catch (error) { errors.push(error) }
    const results = await Promise.allSettled([user.api.dispose(), page.context().close()])
    errors.push(...results.filter(result => result.status === 'rejected').map(result => result.reason))
    try { await deleteIdentity(user.subject) } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'User fixture failed')
  },
  sharedUser: async ({ browser, contextOptions, workerSharedUser }, provide) => {
    const context = await createSharedUserContext(browser, workerSharedUser, contextOptions)
    const exceptions = browserErrors(context)
    const page = await context.newPage()
    const api = await Api.create(workerSharedUser.page)
    const user: User = {
      subject: workerSharedUser.identity.subject,
      email: workerSharedUser.identity.email,
      password: workerSharedUser.identity.password,
      account: workerSharedUser.account,
      page,
      api,
    }
    const data = new Data(user)
    user.data = data
    const errors: unknown[] = []
    try {
      await provide(user)
    } catch (error) {
      errors.push(error)
    }
    try {
      await data.cleanup()
    } catch (error) {
      errors.push(error)
    }
    const results = await Promise.allSettled([api.dispose(), context.close()])
    errors.push(...results.filter(r => r.status === 'rejected').map(r => r.reason))
    errors.push(...exceptions)
    if (errors.length) throw new AggregateError(errors, 'Shared user fixture failed')
  },
  secondary: async ({ browser, contextOptions }, provide) => {
    const context = await browser.newContext({ ...contextOptions, baseURL: webURL })
    await installLocalhostCookieFix(context)
    const exceptions = browserErrors(context)
    let user: User | undefined
    const errors: unknown[] = []
    try {
      user = await createUser(await context.newPage())
      await provide(user)
    } catch (error) { errors.push(error) }
    const results = await Promise.allSettled([user?.api.dispose(), context.close()])
    errors.push(...results.filter(result => result.status === 'rejected').map(result => result.reason))
    errors.push(...exceptions)
    if (user) try { await deleteIdentity(user.subject) } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'Secondary user fixture failed')
  },
  guest: async ({ browser, contextOptions }, provide) => {
    const context = await browser.newContext({ ...contextOptions, baseURL: webURL, storageState: undefined })
    await installLocalhostCookieFix(context)
    const errors: unknown[] = browserErrors(context)
    try { await provide(await context.newPage()) } catch (error) { errors.push(error) }
    try { await context.close() } catch (error) { errors.push(error) }
    if (errors.length) throw new AggregateError(errors, 'Guest fixture failed')
  },
  data: async ({ user }, provide) => {
    const data = new Data(user)
    try { await provide(data) } finally { await data.cleanup() }
  },
  sharedData: async ({ sharedUser }, provide) => {
    const data = sharedUser.data ?? new Data(sharedUser)
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
