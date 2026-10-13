import { randomUUID } from 'node:crypto'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { pathToFileURL } from 'node:url'

export function structuredCompletion(value: unknown) {
  return { id: `chatcmpl-${randomUUID()}`, object: 'chat.completion', created: 1, model: 'openai/gpt-6.1-sol', choices: [{ index: 0, message: { role: 'assistant', content: JSON.stringify(value) }, finish_reason: 'stop' }], usage: { prompt_tokens: 30, completion_tokens: 40, total_tokens: 70 } }
}

type ResponseStep = { status: number; body?: unknown; chunks?: unknown[]; pauseAfter?: number; hold?: boolean; requiredInput?: string[] }
export type Scenario = {
  id: string
  path: '/chat/completions' | '/decisions'
  contains: string
  responses: ResponseStep[]
}
type Registered = Scenario & { consumed: number; active: number; release: Set<() => void> }

function validScenario(value: unknown): value is Scenario {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<Scenario>
  return typeof item.id === 'string' && /^[a-z0-9-]{12,80}$/.test(item.id)
    && ['/chat/completions', '/decisions'].includes(item.path ?? '')
    && typeof item.contains === 'string' && item.contains.trim().length >= 3 && item.contains.length <= 2048
    && Array.isArray(item.responses) && item.responses.length > 0 && item.responses.length <= 20
    && item.responses.every(step => Number.isInteger(step.status) && step.status >= 200 && step.status <= 599
      && (step.hold === undefined || typeof step.hold === 'boolean')
      && (step.requiredInput === undefined || Array.isArray(step.requiredInput) && step.requiredInput.every(value => typeof value === 'string' && value.length > 0))
      && (step.pauseAfter === undefined || Number.isInteger(step.pauseAfter) && step.pauseAfter > 0 && Array.isArray(step.chunks) && step.pauseAfter < step.chunks.length)
      && ((step.body !== undefined && step.chunks === undefined)
        || (step.body === undefined && Array.isArray(step.chunks) && step.chunks.length > 0 && step.chunks.length <= 1000)))
}

async function body(request: IncomingMessage) {
  const chunks: Buffer[] = []
  let bytes = 0
  for await (const chunk of request) {
    bytes += chunk.length
    if (bytes > 1_048_576) throw new Error('Request body exceeds limit')
    chunks.push(Buffer.from(chunk))
  }
  return JSON.parse(Buffer.concat(chunks).toString()) as unknown
}

function json(response: ServerResponse, status: number, value: unknown) {
  response.writeHead(status, { 'content-type': 'application/json' })
  response.end(JSON.stringify(value))
}

function waitForRelease(scenario: Registered, response: ServerResponse) {
  return new Promise<void>(resolve => {
    const release = () => { scenario.release.delete(release); response.off('close', release); resolve() }
    scenario.release.add(release)
    response.once('close', release)
  })
}

export function modelProvider() {
  const scenarios = new Map<string, Registered>()
  const unexpected: { path: string; reason: string }[] = []
  return createServer(async (request, response) => {
    const path = request.url ?? ''
    try {
      if (request.method === 'GET' && path === '/health') return json(response, 200, { ready: true })
      if (request.method === 'GET' && path === '/unexpected') return json(response, 200, unexpected)
      if (request.method === 'POST' && path === '/scenarios') {
        const item = await body(request)
        if (!validScenario(item)) return json(response, 400, { error: 'Invalid scenario' })
        if (scenarios.has(item.id)) return json(response, 409, { error: 'Scenario already exists' })
        scenarios.set(item.id, { ...item, consumed: 0, active: 0, release: new Set() })
        return json(response, 201, { id: item.id })
      }
      if (path.startsWith('/scenarios/')) {
        const id = path.slice('/scenarios/'.length).replace(/\/release$/, '')
        const scenario = scenarios.get(id)
        if (!scenario) return json(response, 404, { error: 'Scenario not found' })
        if (request.method === 'POST' && path.endsWith('/release')) {
          for (const release of scenario.release) release()
          return json(response, 200, { released: true })
        }
        if (request.method === 'GET') return json(response, 200, { consumed: scenario.consumed, expected: scenario.responses.length, active: scenario.active })
        if (request.method === 'DELETE') {
          if (scenario.active) return json(response, 409, { error: 'Scenario still streaming' })
          scenarios.delete(id)
          return json(response, 200, { removed: true })
        }
      }
      if (request.method !== 'POST' || !['/chat/completions', '/decisions'].includes(path)) {
        return json(response, 404, { error: 'Unknown protocol route' })
      }
      const input = JSON.stringify(await body(request))
      const matches = [...scenarios.values()].filter(item => item.path === path && input.includes(item.contains))
      const scenario = matches.length === 1 ? matches[0] : undefined
      const step = scenario?.responses[scenario.consumed]
      if (!scenario || !step) {
        unexpected.push({ path, reason: matches.length > 1 ? 'ambiguous' : scenario ? 'exhausted' : 'unmatched' })
        return json(response, 500, { error: { message: 'No unique available E2E scenario', type: 'scenario_error' } })
      }
      scenario.consumed++
      if (step.requiredInput?.some(value => !input.includes(value))) {
        unexpected.push({ path, reason: 'input-contract-mismatch' })
        return json(response, 500, { error: { message: 'E2E provider input contract mismatch', type: 'scenario_error' } })
      }
      if (step.hold) {
        scenario.active++
        try { await waitForRelease(scenario, response) } finally { scenario.active-- }
        if (response.destroyed) return
      }
      if (!step.chunks) return json(response, step.status, step.body)
      response.writeHead(step.status, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
      scenario.active++
      try {
        for (const [index, chunk] of step.chunks.entries()) {
          if (response.destroyed) break
          response.write(`data: ${JSON.stringify(chunk)}\n\n`)
          if (index + 1 === step.pauseAfter) await waitForRelease(scenario, response)
        }
        if (!response.destroyed) response.end('data: [DONE]\n\n')
      } finally { scenario.active-- }
    } catch {
      if (!response.headersSent) json(response, 400, { error: 'Invalid provider request' })
      else response.end()
    }
  })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = modelProvider().listen(8110, '0.0.0.0')
  process.once('SIGTERM', () => server.close())
  process.once('SIGINT', () => server.close())
}
