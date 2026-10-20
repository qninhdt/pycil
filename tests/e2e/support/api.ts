import { request, type APIRequestContext, type Page } from '@playwright/test'
import { apiURL } from './environment.ts'

export type Account = { id: string; handle: string | null; display_name: string | null; bio: string | null; library_node_id: string; personal_node_id: string; published_node_id: string; plan: string; settings: { locale: string; timezone: string; translation_language: string } }
export type Node = { id: string; name: string; type: string; owner_id: string }

export class Api {
  private client: APIRequestContext
  private page?: Page
  constructor(client: APIRequestContext, page?: Page) { this.client = client; this.page = page }

  static async create(page?: Page) {
    return new Api(await request.newContext({ baseURL: `${apiURL}/v1/`, timeout: 30_000, ignoreHTTPSErrors: true }), page)
  }

  async call<T>(path: string, method = 'GET', data?: unknown, expectedStatus: number | number[] = 200): Promise<T> {
    if (this.page) await this.page.waitForFunction(() => Boolean(window.Clerk?.loaded && window.Clerk.session), undefined, { timeout: 15_000 })
    const token = this.page ? await this.page.evaluate(async () => {
      const token = await window.Clerk.session?.getToken()
      if (!token) throw new Error('A real Clerk session is required')
      return token
    }) : null
    const response = await this.client.fetch(`./${path}`, {
      method, data, headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    const allowed = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus]
    if (!allowed.includes(response.status())) throw new Error(`${method} ${path.split('?')[0]}: expected HTTP ${allowed.join('/')}, received ${response.status()}`)
    return (response.status() === 204 ? null : await response.json()) as T
  }

  dispose() { return this.client.dispose() }
}
