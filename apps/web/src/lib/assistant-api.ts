import { MessageSchema, type Message, type RunAgentInput } from '@ag-ui/core'
import { HomeApiError, homeRequest, homeToken } from './home-api'

export type ReasoningEffort = 'low' | 'medium' | 'high'
export const REASONING_EFFORTS: readonly ReasoningEffort[] = ['low', 'medium', 'high'] as const
export type AssistantModel = { id: string; name: string; vision: boolean; efforts: string[] }
export type Conversation = { id: string; title: string | null; updated_at: string }
export type Approval = { interrupt_id: string; action_requests: { name: string; args: Record<string, unknown>; description?: string | null }[] }
export type ConversationDetails = Conversation & { state: { messages: Message[]; pending_approvals: Approval[] } }
export type ConversationPage = { conversations: Conversation[]; next_cursor: string | null }
export type AssistantService = ReturnType<typeof createAssistantService>

export class AssistantError extends Error {
  constructor(public status: number, public code: string) {
    super(status === 401 ? 'Sign in again to continue with PycilAI.'
      : code === 'allowance_exhausted' ? 'Your AI allowance is exhausted. Check the reset date before starting another response.'
      : status === 429 ? 'Your assistant allowance or request limit was reached. Try again later.'
      : code === 'conversation_busy' ? 'This conversation is busy. Wait a moment, then reopen it.'
      : code === 'approval_pending' ? 'Review the pending Library changes before sending another message.'
      : status === 413 ? 'The message is too large. Use fewer or smaller images.'
      : 'PycilAI could not complete the request. Reopen this conversation to check its saved state.')
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AssistantError(502, 'invalid_response')
  return value as Record<string, unknown>
}
function conversation(value: unknown): Conversation {
  const item = record(value)
  if (typeof item.id !== 'string' || typeof item.updated_at !== 'string' || !Number.isFinite(Date.parse(item.updated_at)) || item.title !== null && typeof item.title !== 'string') throw new AssistantError(502, 'invalid_response')
  return { id: item.id, title: item.title as string | null, updated_at: item.updated_at }
}
export function parseConversationDetails(value: unknown): ConversationDetails {
  const item = record(value), state = record(item.state)
  if (!Array.isArray(state.messages) || !Array.isArray(state.pending_approvals)) throw new AssistantError(502, 'invalid_response')
  const messages = state.messages.map(message => {
    const parsed = MessageSchema.safeParse(message)
    if (!parsed.success) throw new AssistantError(502, 'invalid_response')
    return parsed.data
  })
  const pending_approvals = state.pending_approvals.map(value => {
    const approval = record(value)
    if (typeof approval.interrupt_id !== 'string' || !Array.isArray(approval.action_requests) || !approval.action_requests.length) throw new AssistantError(502, 'invalid_response')
    return { interrupt_id: approval.interrupt_id, action_requests: approval.action_requests.map(value => {
      const action = record(value)
      if (typeof action.name !== 'string' || action.description != null && typeof action.description !== 'string') throw new AssistantError(502, 'invalid_response')
      return { name: action.name, args: record(action.args), description: action.description as string | null | undefined }
    }) }
  })
  return { ...conversation(item), state: { messages, pending_approvals } }
}

// The server owns history and tools: send only the new turn or the approval resolution.
export function turnInput(input: RunAgentInput, threadId: string, model: AssistantModel, effort: string): RunAgentInput {
  if (!model.efforts.includes(effort) || !REASONING_EFFORTS.includes(effort as ReasoningEffort)) throw new Error('Select a supported reasoning effort.')
  const messages = input.resume?.length ? [] : input.messages.slice(-1)
  if (!input.resume?.length && (messages.length !== 1 || messages[0].role !== 'user')) throw new Error('Enter a new message to continue.')
  let chars = 0, images = 0
  for (const message of messages) {
    if (typeof message.content === 'string') chars += message.content.length
    else if (Array.isArray(message.content)) for (const part of message.content) {
      if (part.type === 'text') chars += part.text.length
      else if (part.type === 'image') {
        images++
        if (!model.vision || part.source.type !== 'data' || !['image/png', 'image/jpeg', 'image/webp'].includes(part.source.mimeType ?? '')) throw new Error('Choose a vision model and a PNG, JPEG or WebP image.')
        if (part.source.value.length * 3 / 4 > 10_000_002) throw new Error('Each image must be at most 10 MB.')
      } else throw new Error('PycilAI supports text and images only.')
    }
  }
  if (chars > 8000 || images > 4) throw new Error('Use up to 8,000 characters and four images per message.')
  const body = { threadId, runId: input.runId, messages, state: {}, tools: [], context: [], forwardedProps: { model_id: model.id, effort }, ...(input.resume?.length ? { resume: input.resume } : {}) }
  if (new TextEncoder().encode(JSON.stringify(body)).length > 15_000_000) throw new Error('Use fewer or smaller images. The complete message must fit within 15 MB.')
  return body
}

export function createAssistantService(getToken: () => Promise<string | null>) {
  async function request<T>(path: string, parse: (value: unknown) => T, signal: AbortSignal, body?: unknown) {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(12000)])
    try { return await homeRequest(`assistant/${path}`, await homeToken(getToken, bounded), parse, bounded, body, body ? 'POST' : undefined) }
    catch (error) {
      if (error instanceof HomeApiError) throw new AssistantError(error.status, error.code)
      throw error
    }
  }
  return {
    models: (signal: AbortSignal) => request('models', value => {
      if (!Array.isArray(value)) throw new AssistantError(502, 'invalid_response')
      return value.map(value => {
        const item = record(value)
        if (typeof item.id !== 'string' || typeof item.name !== 'string' || typeof item.vision !== 'boolean' || !Array.isArray(item.efforts) || !item.efforts.length || item.efforts.some(effort => typeof effort !== 'string')) throw new AssistantError(502, 'invalid_response')
        return item as AssistantModel
      })
    }, signal),
    list: (cursor: string | undefined, signal: AbortSignal) => request(`conversations?${new URLSearchParams({ limit: '20', ...(cursor ? { cursor } : {}) })}`, value => {
      const item = record(value)
      if (!Array.isArray(item.conversations) || item.next_cursor !== null && typeof item.next_cursor !== 'string') throw new AssistantError(502, 'invalid_response')
      return { conversations: item.conversations.map(conversation), next_cursor: item.next_cursor as string | null }
    }, signal),
    create: (title: string, signal: AbortSignal) => request('conversations', conversation, signal, { title: title.slice(0, 255) }),
    remove: async (id: string, signal: AbortSignal) => {
      const bounded = AbortSignal.any([signal, AbortSignal.timeout(12000)])
      try { await homeRequest(`assistant/conversations/${encodeURIComponent(id)}`, await homeToken(getToken, bounded), () => undefined, bounded, undefined, 'DELETE') }
      catch (error) { if (error instanceof HomeApiError) throw new AssistantError(error.status, error.code); throw error }
    },
    details: (id: string, signal: AbortSignal) => request(`conversations/${encodeURIComponent(id)}`, parseConversationDetails, signal),
    run: async (input: RunAgentInput, signal: AbortSignal) => {
      const response = await fetch('/api/v1/assistant:run', { method: 'POST', headers: { Authorization: `Bearer ${await homeToken(getToken, signal)}`, 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify(input), signal })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new AssistantError(response.status, typeof body?.error === 'string' ? body.error : 'request_failed')
      }
      if (!response.headers.get('content-type')?.includes('text/event-stream')) throw new AssistantError(502, 'invalid_stream')
      return response
    },
  }
}
