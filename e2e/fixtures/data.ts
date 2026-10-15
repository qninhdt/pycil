import type { User } from './users.ts'
import type { Node } from '../support/api.ts'
import { readFile } from 'node:fs/promises'
import { artifacts } from '../support/environment.ts'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { runId } from '../support/environment.ts'

export type Vocabulary = Record<'bankFinancial' | 'bankRiver' | 'bankDeposit' | 'archiveCollection' | 'colorAppearance', { word_id: number; sense_id: number }> & { pagination: { word_id: number; sense_id: number; lemma: string; definition: string }[] }
export async function vocabulary(): Promise<Vocabulary> {
  const value = JSON.parse(await readFile(`${artifacts}/vocabulary.json`, 'utf8')) as Vocabulary
  for (const key of ['bankFinancial', 'bankRiver', 'bankDeposit', 'archiveCollection', 'colorAppearance'] as const) {
    if (!Number.isSafeInteger(value[key]?.sense_id) || value[key].sense_id <= 0 || !Number.isSafeInteger(value[key].word_id)) throw new Error(`Invalid baseline manifest entry: ${key}`)
  }
  if (value.pagination.length !== 101 || new Set(value.pagination.map(item => item.sense_id)).size !== 101) throw new Error('Pagination baseline must contain 101 distinct senses')
  return value
}

export class Data {
  private nodes = new Set<string>()
  constructor(private user: User) {}

  track(id: string) { this.nodes.add(id); return id }

  async prepareUser(options: { plan?: 'free' | 'pro'; exhausted?: boolean; dueSense?: number }) {
    const runtime = JSON.parse(await readFile(`${artifacts}/runtime.json`, 'utf8')) as { runId: string; project: string; apiContainer: string }
    if (runtime.runId !== runId || runtime.project !== `pycil-e2e-${runId}` || !/^[a-f0-9]{64}$/.test(runtime.apiContainer)) throw new Error('Invalid owned stack manifest')
    const execute = promisify(execFile)
    const { stdout } = await execute('docker', ['inspect', '--format', '{{index .Config.Labels "com.docker.compose.project"}}', runtime.apiContainer])
    if (stdout.trim() !== runtime.project) throw new Error('User setup refused a container outside this run')
    const args = ['exec', runtime.apiContainer, 'python', '/e2e/seed.py', 'user', '--user-id', this.user.account.id]
    if (options.plan) args.push('--plan', options.plan)
    if (options.exhausted) args.push('--exhausted')
    if (options.dueSense !== undefined) {
      if (!Number.isSafeInteger(options.dueSense) || options.dueSense <= 0) throw new Error('Invalid due sense')
      args.push('--due-sense', String(options.dueSense))
    }
    try { await execute('docker', args, { timeout: 30_000 }) }
    catch { throw new Error('Owned user fixture preparation failed') }
    this.user.account = await this.user.api.call('me')
  }

  async create(input: { name: string; type: 'folder' | 'deck' | 'reference'; parent_id?: string; reference_id?: string; sense_ids?: number[] }) {
    const node = await this.user.api.call<Node>('nodes', 'POST', { parent_id: this.user.account.personal_node_id, ...input }, 201)
    this.track(node.id)
    return node
  }

  async cleanup() {
    const results = await Promise.allSettled([...this.nodes].reverse().map(id => this.user.api.call(`nodes/${id}`, 'DELETE', undefined, [204, 404])))
    const errors = results.filter(result => result.status === 'rejected').map(result => result.reason)
    if (errors.length) throw new AggregateError(errors, 'Owned node cleanup failed')
  }
}
