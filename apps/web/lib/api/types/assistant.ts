/**
 * Assistant threads, the model catalog, and the credit projection.
 *
 * The stream itself has no type here: `@assistant-ui/react-ag-ui` consumes the
 * AG-UI event protocol, and a hand-written event union alongside it would be a
 * second, unvalidated description of the same wire format.
 */

export interface Thread {
  id: string
  title: string
  status: string
  createdAt: string | null
  updatedAt: string | null
}

export interface ThreadCreate {
  title?: string
}

export interface MessageCreate {
  clientMessageId: string
  content: string
}

/**
 * One selectable model, from `GET /v1/assistant/models`.
 *
 * The server owns this catalog: a client selects from what it is offered and never
 * supplies a model id or a price the server has not published.
 */
export interface ModelPricing {
  inputUsdPerM: number
  outputUsdPerM: number
  cachedReadUsdPerM: number
}

export interface ModelRead {
  id: string
  name: string
  provider: string
  vision: boolean
  reasoning: boolean
  supportedEfforts: string[]
  contextWindow: number
  maxOutputTokens: number
  pricing: ModelPricing
  isDefault: boolean
}

export interface ModelCatalog {
  defaultModel: string
  defaultReasoningEffort: string
  models: ModelRead[]
}

/**
 * The learner's monthly allowance, from `GET /v1/me/credit`.
 *
 * Credits, never currency: `available` is the balance clamped at zero for display,
 * while `balance` stays signed because an admitted turn may finish past it.
 */
export interface AccountCredit {
  plan: string
  balance: number
  available: number
  periodStart: string
  periodEnd: string
  periodUsed: number
  periodGrant: number
  topupBalance: number
}

export type ActionDecision = "approve" | "reject"

export interface ResumePayload {
  decision: ActionDecision
}

// `AccountExport` lives in ./auth: `/v1/me/export` is an account endpoint, and
// the assistant section of it is one opaque member among five.
