import { test as base, expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import type { AccountProfile } from '../src/lib/api'
import { setupClerkTestingToken } from '@clerk/testing/playwright'

export async function signIn(page: Page, account: 'A' | 'B' | 'C' = 'A', loginPath = '/login') {
  const email = process.env[`E2E_EMAIL_${account}`], password = process.env[`E2E_PASSWORD_${account}`]
  if (!email || !password) throw new Error(`Set E2E_EMAIL_${account} and E2E_PASSWORD_${account} for a dedicated Clerk test identity.`)
  await setupClerkTestingToken({ page })
  await page.goto(loginPath)
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled()
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email)
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await verifyDevice(page)
  const profile = await api<AccountProfile>(page, 'me')
  expect(profile.status).toBe(200)
  return profile.body
}

export async function signOut(page: Page) {
  await page.goto('/app')
  await api<AccountProfile>(page, 'me')
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText(/Free plan|Pro plan/)
  await page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled()
}

export async function verifyDevice(page: Page) {
  const code = page.getByLabel('Verification code', { exact: true })
  await expect.poll(async () => /\/app(?:\/|\?|$)/.test(new URL(page.url()).pathname) || await code.isVisible()).toBe(true)
  if (await code.isVisible()) {
    await code.fill('424242')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  }
  await expect(page).toHaveURL(/\/app(?:\/|\?|$)/)
}

export async function api<T = unknown>(page: Page, path: string, method = 'GET', body?: unknown, authenticated = true, headers: Record<string, string> = {}) {
  if (authenticated) await page.waitForFunction(() => Boolean((window as unknown as { Clerk?: { session?: unknown } }).Clerk?.session), undefined, { timeout: 15000 })
  return page.evaluate(async ({ path, method, body, authenticated, headers }) => {
    const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } }).Clerk
    const token = authenticated ? await clerk?.session?.getToken() : null
    if (authenticated && !token) throw new Error('The live test requires a real Clerk session token.')
    const response = await fetch(`/api/v1/${path}`, {
      method, cache: 'no-store', headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    return { status: response.status, body: response.status === 204 ? null : await response.json() }
  }, { path, method, body, authenticated, headers }) as Promise<{ status: number; body: T }>
}

type Node = { id: string; name: string; sense_ids?: number[]; parent_id: string; space: string }
type Fixtures = {
  profile: AccountProfile
  nodes: { create: (input: { type: 'FOLDER' | 'DECK'; name?: string; parent_id?: string; sense_ids?: number[] }) => Promise<Node>; track: (id: string) => void }
}

export const test = base.extend<Fixtures>({
  profile: async ({ page }, provide) => { await provide(await signIn(page)) },
  nodes: async ({ page, profile }, provide) => {
    const owned = new Set<string>()
    try { await provide({
      track: id => { owned.add(id) },
      create: async input => {
        const response = await api<Node>(page, 'nodes', 'POST', { ...input, name: input.name ?? `e2e-${randomUUID()}`, parent_id: input.parent_id ?? profile.personal_node_id, ...(input.type === 'DECK' ? { sense_ids: input.sense_ids ?? [] } : {}) })
        expect(response.status).toBe(201)
        owned.add(response.body.id)
        return response.body
      },
    }) } finally {
      const failures: string[] = []
      for (const id of [...owned].reverse()) {
        try {
          const result = await api(page, `nodes/${encodeURIComponent(id)}`, 'DELETE')
          if (![204, 404].includes(result.status)) failures.push(`${id}: HTTP ${result.status}`)
        } catch { failures.push(`${id}: cleanup request failed`) }
      }
      expect(failures, 'Cleanup of test-owned nodes').toEqual([])
    }
  },
})

export { expect }
export const proTest = test.extend<Fixtures>({ profile: async ({ page }, provide) => { await provide(await signIn(page, 'B')) } })
