import { createClerkClient } from '@clerk/backend'
import { isClerkAPIResponseError } from '@clerk/backend/errors'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { appendFile, mkdir, readFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { expect, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { artifacts, runId, webURL } from '../support/environment.ts'
import { Api, type Account } from '../support/api.ts'
import type { Data } from './data.ts'

const backend = () => createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY! })
export type User = { subject: string; email: string; password: string; page: Page; api: Api; account: Account; data?: Data }

export function identityFailure(error: unknown) {
  return isClerkAPIResponseError(error)
    ? new Error(`Clerk identity request failed (HTTP ${error.status}; ${error.errors.map(item => item.code).join(', ')})`)
    : error
}

function identityTransportFailure(error: unknown) {
  return isClerkAPIResponseError(error) && (error.status === undefined || error.errors.some(item => item.code === 'unexpected_error'))
}

export function isRateLimitError(error: unknown): boolean {
  if (isClerkAPIResponseError(error)) {
    return error.status === 429 || error.errors.some(item => item.code === 'rate_limit_exceeded')
  }
  if (error && typeof error === 'object') {
    if ('status' in error && (error as { status: unknown }).status === 429) return true
    if ('message' in error && typeof (error as { message: unknown }).message === 'string' && (error as { message: string }).message.includes('HTTP 429')) return true
    if (error instanceof AggregateError) {
      return error.errors.some(isRateLimitError)
    }
  }
  return false
}

export type RetryOptions = {
  maxAttempts?: number
  initialDelayMs?: number
  maxDelayMs?: number
  jitterRatio?: number
}

export async function withClerkRetry<T>(
  action: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const { maxAttempts = 5, initialDelayMs = 250, maxDelayMs = 5000, jitterRatio = 0.25 } = options
  let attempt = 0
  while (true) {
    try {
      return await action()
    } catch (error) {
      attempt++
      if (attempt >= maxAttempts || !isRateLimitError(error)) {
        throw error
      }
      let baseDelay = initialDelayMs * Math.pow(2, attempt - 1)
      if (isClerkAPIResponseError(error) && typeof error.retryAfter === 'number' && error.retryAfter > 0) {
        baseDelay = Math.max(baseDelay, error.retryAfter * 1000)
      }
      baseDelay = Math.min(baseDelay, maxDelayMs)
      const minJitter = 1 - jitterRatio
      const maxJitter = 1 + jitterRatio
      const delay = Math.round(baseDelay * (minJitter + Math.random() * (maxJitter - minJitter)))
      console.warn(`Clerk fixture: rate limit (HTTP 429) encountered. Retrying in ${delay}ms (attempt ${attempt}/${maxAttempts})...`)
      await new Promise(resolve => setTimeout(resolve, delay))
    }
  }
}

export async function createSignInToken(
  clientOrUserId: ReturnType<typeof createClerkClient> | string,
  maybeUserId?: string,
  expiresInSeconds = 300,
  retryOptions?: RetryOptions
) {
  let client: ReturnType<typeof createClerkClient>
  let userId: string
  if (typeof clientOrUserId === 'string') {
    client = backend()
    userId = clientOrUserId
  } else {
    client = clientOrUserId
    userId = maybeUserId!
  }
  return await withClerkRetry(
    () => client.signInTokens.createSignInToken({ userId, expiresInSeconds }),
    retryOptions
  )
}

export async function provisionIdentity(
  client: ReturnType<typeof createClerkClient>,
  email: string,
  password: string,
  retryOptions?: RetryOptions
) {
  return await withClerkRetry(async () => {
    try { return await client.users.createUser({ emailAddress: [email], password }) }
    catch (error) {
      if (!identityTransportFailure(error)) throw error
      console.warn('Clerk fixture: creation lost its response; checking the reserved email before one bounded retry.')
      const users = await client.users.getUserList({ emailAddress: [email] })
      const existing = users.data.find(user => user.emailAddresses.some(address => address.emailAddress === email))
      return existing ?? await client.users.createUser({ emailAddress: [email], password })
    }
  }, retryOptions)
}

export async function deleteIdentityUser(client: ReturnType<typeof createClerkClient>, subject: string) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try { await client.users.deleteUser(subject); return }
    catch (error) {
      if (isClerkAPIResponseError(error) && error.status === 404) return
      if (attempt >= 1 || !identityTransportFailure(error)) throw identityFailure(error)
      console.warn(`Clerk fixture: deletion lost its response (attempt ${attempt + 1}); retrying the owned identity.`, error)
      await new Promise(r => setTimeout(r, 1000))
    }
  }
}

export async function reserveIdentity() {
  const email = `pycil-${runId}-${randomUUID().slice(0, 8)}+clerk_test@example.com`
  const password = `${randomUUID()}!aA7`
  await mkdir(artifacts, { recursive: true, mode: 0o700 })
  await appendFile(`${artifacts}/identities.jsonl`, JSON.stringify({ email }) + '\n', { mode: 0o600 })
  return { email, password }
}

export async function removeReservedIdentity(email: string) {
  if (!email.startsWith(`pycil-${runId}-`) || !email.endsWith('+clerk_test@example.com')) throw new Error('Identity does not belong to this run')
  const users = await backend().users.getUserList({ emailAddress: [email] })
  await Promise.all(users.data.filter(user => user.emailAddresses.some(address => address.emailAddress === email)).map(user => deleteIdentity(user.id)))
}

export async function createIdentity() {
  const { email, password } = await reserveIdentity()
  const user = await provisionIdentity(backend(), email, password).catch(error => { throw identityFailure(error) })
  await appendFile(`${artifacts}/identities.jsonl`, JSON.stringify({ email, id: user.id }) + '\n', { mode: 0o600 })
  return { subject: user.id, email, password }
}

export async function signIn(page: Page, email: string, password: string, destination: string) {
  await setupClerkTestingToken({ page })
  // Clerk's testing route assumes JSON; handshake legitimately redirects to HTML.
  await page.context().route('**/v1/client/handshake?**', route => route.continue())
  await page.context().clearCookies({ name: '__clerk_redirect_count' })
  await page.goto(`/login?returnTo=${encodeURIComponent(destination)}`)
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const code = page.getByLabel('Verification code', { exact: true })
  await expect.poll(async () => new URL(page.url()).pathname === destination || await code.isVisible()).toBe(true)
  if (await code.isVisible()) {
    await code.fill('424242')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  }
  await expect.poll(() => new URL(page.url()).pathname).toBe(destination)
}

async function attemptCreateUser(page: Page): Promise<User> {
  const identity = await createIdentity()
  let api: Api | undefined
  try {
    await setupClerkTestingToken({ page })
    await page.context().route('**/v1/client/handshake?**', route => route.continue())
    await page.context().addCookies([
      {
        name: '__client_uat',
        value: String(Math.floor(Date.now() / 1000) - 5),
        url: 'http://localhost:3200',
      },
    ])
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await page.goto('/login')
        break
      } catch (e: any) {
        if (attempt < 2 && (e?.message?.includes('ERR_NETWORK_CHANGED') || e?.message?.includes('chromewebdata') || e?.message?.includes('interrupted by another navigation'))) {
          await new Promise(r => setTimeout(r, 500))
          continue
        }
        throw e
      }
    }
    await page.waitForFunction(() => window.Clerk !== undefined && Boolean(window.Clerk.loaded), undefined, { timeout: 30_000 })
    const ticketToken = await createSignInToken(backend(), identity.subject, 300)
    const signInResult = await page.evaluate(async (ticket) => {
      try {
        const client = window.Clerk?.client
        if (!client) throw new Error('window.Clerk.client is missing')
        const signInRes = await client.signIn.create({ strategy: 'ticket', ticket })
        if (signInRes.status !== 'complete') throw new Error(`Status is ${signInRes.status}`)
        await window.Clerk.setActive({ session: signInRes.createdSessionId })
        return { ok: true }
      } catch (err: any) {
        return { ok: false, message: err?.message, errors: err?.errors }
      }
    }, ticketToken.token)
    if (!signInResult.ok) throw new Error(`Client signIn failed: ${signInResult.message || 'unknown error'}`)
    await page.context().clearCookies({ name: '__clerk_redirect_count' })
    await page.evaluate(() => {
      if (window.location.hostname === 'localhost' || !window.location.hostname.includes('.')) {
        const session = window.Clerk?.session
        const uat = session?.lastActiveAt
          ? Math.floor(new Date(session.lastActiveAt).getTime() / 1000)
          : Math.floor(Date.now() / 1000) - 5
        document.cookie = `__client_uat=${uat}; path=/; max-age=31536000; samesite=lax`
      }
    })
    try {
      await page.goto('/auth/complete?returnTo=%2Fapp')
    } catch (e: any) {
      if (e?.message?.includes('ERR_NETWORK_CHANGED')) {
        await page.goto('/auth/complete?returnTo=%2Fapp')
      } else {
        throw e
      }
    }
    await expect.poll(() => new URL(page.url()).pathname).toBe('/app')
    await page.waitForFunction(() => window.Clerk !== undefined && Boolean(window.Clerk.loaded), undefined, { timeout: 30_000 })
    api = await Api.create(page)
    const account = await api.call<Account>('me')
    return { ...identity, page, api, account }
  } catch (cause) {
    const failure = identityFailure(cause)
    const results = await Promise.allSettled([api?.dispose(), deleteIdentity(identity.subject)])
    const errors = results.filter(result => result.status === 'rejected').map(result => result.reason)
    if (errors.length) throw new AggregateError([failure, ...errors], 'User setup and cleanup failed')
    throw failure
  }
}

export async function createUser(page: Page, retryOptions?: RetryOptions): Promise<User> {
  return await withClerkRetry(() => attemptCreateUser(page), retryOptions)
}

export async function installLocalhostCookieFix(context: BrowserContext) {
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

export type WorkerCachedUser = {
  identity: { subject: string; email: string; password: string }
  account: Account
  storageStatePath: string
  storageState: { cookies: unknown[]; origins: unknown[] }
  page: Page
  context: BrowserContext
  api: Api
  dispose: () => Promise<void>
}

export async function createWorkerUser(browser: Browser, workerIndex: number): Promise<WorkerCachedUser> {
  await mkdir(artifacts, { recursive: true, mode: 0o700 })
  const storageStatePath = `${artifacts}/worker-storage-${workerIndex}.json`
  const context = await browser.newContext({
    baseURL: webURL,
    ignoreHTTPSErrors: true,
  })
  await installLocalhostCookieFix(context)
  const page = await context.newPage()
  const user = await createUser(page)
  await context.storageState({ path: storageStatePath })
  const storageState = JSON.parse(await readFile(storageStatePath, 'utf8'))
  return {
    identity: {
      subject: user.subject,
      email: user.email,
      password: user.password,
    },
    account: user.account,
    storageStatePath,
    storageState,
    page: user.page,
    context,
    api: user.api,
    dispose: async () => {
      const results = await Promise.allSettled([
        user.api.dispose(),
        context.close(),
        deleteIdentity(user.subject),
      ])
      const errors = results.filter(r => r.status === 'rejected').map(r => r.reason)
      if (errors.length) throw new AggregateError(errors, 'Worker user cleanup failed')
    },
  }
}

export async function createSharedUserContext(
  browser: Browser,
  workerUser: WorkerCachedUser,
  contextOptions?: Parameters<Browser['newContext']>[0]
) {
  const context = await browser.newContext({
    ...contextOptions,
    baseURL: webURL,
    storageState: workerUser.storageStatePath,
    ignoreHTTPSErrors: true,
  })
  await installLocalhostCookieFix(context)
  await setupClerkTestingToken({ context })
  await context.route('**/v1/client/handshake?**', route => route.continue())
  return context
}

export async function deleteIdentity(subject: string) {
  await deleteIdentityUser(backend(), subject)
  await appendFile(`${artifacts}/identities.jsonl`, JSON.stringify({ id: subject, deleted: true }) + '\n', { mode: 0o600 })
}

export async function cleanupIdentities() {
  let ledger: string
  try { ledger = await readFile(`${artifacts}/identities.jsonl`, 'utf8') }
  catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return
    throw error
  }
  const entries = ledger.trim().split('\n').filter(Boolean).map(line => JSON.parse(line) as { email?: string; id?: string; deleted?: boolean })
  const deleted = new Set(entries.filter(item => item.deleted).map(item => item.id))
  const accounts = new Map<string, string | undefined>()
  for (const entry of entries) if (entry.email) {
    if (!entry.email.startsWith(`pycil-${runId}-`) || !entry.email.endsWith('+clerk_test@example.com')) throw new Error('Identity ledger contains an unowned email')
    accounts.set(entry.email, entry.id)
  }
  const ids = new Set([...accounts.values()].filter((id): id is string => !!id && !deleted.has(id)))
  for (const [email, id] of accounts) {
    if (id) continue
    const users = await backend().users.getUserList({ emailAddress: [email] })
    for (const user of users.data) if (user.emailAddresses.some(address => address.emailAddress === email)) ids.add(user.id)
  }
  const results = await Promise.allSettled([...ids].map(deleteIdentity))
  const errors = results.filter(result => result.status === 'rejected').map(result => result.reason)
  if (errors.length) throw new AggregateError(errors, 'Owned Clerk identity cleanup failed')
}
