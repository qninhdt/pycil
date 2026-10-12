import type { Page } from '@playwright/test'

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
