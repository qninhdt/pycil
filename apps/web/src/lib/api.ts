export type AccountProfile = {
  id: string
  display_name: string | null
  handle: string | null
  bio: string | null
  joined_at: string
  plan: 'free' | 'pro' | 'FREE' | 'PRO'
  personal_node_id: string
  published_node_id: string
  library_node_id: string
  learning_options: {
    pairs: { question_type: string; format: AnswerFormat; level: number }[]
    limits: { min_questions_per_sense: number; max_questions_per_sense: number; max_questions_per_prepare: number }
    advanced_grading: boolean
  }
  settings: { locale: string; timezone: string; translation_language: string; learning: LearningSettings }
  effective_learning: LearningSettings | null
  learning_restriction: string | null
}

export type AnswerFormat = 'SINGLE_CHOICE' | 'SINGLE_WORD' | 'SHORT_ANSWER'
export type LearningSettings = {
  question_types: string[]; formats: AnswerFormat[]; questions_per_sense: number
  max_sense_count: number; show_explanations: boolean
}
export type SettingsPatch = { locale?: string; timezone?: string; translation_language?: string; learning?: Partial<LearningSettings> }
export type PublicProfile = Pick<AccountProfile, 'id' | 'display_name' | 'handle' | 'bio' | 'joined_at' | 'published_node_id'>

export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(status === 401 ? 'Your session could not be verified. Sign in again.'
      : status === 429 ? 'Too many requests. Wait a moment, then retry.'
      : 'Your account could not be loaded. Check your connection and retry.')
  }
}

export function parsePublicProfile(value: unknown): PublicProfile {
  if (!value || typeof value !== 'object') throw new ApiError(502, 'invalid_profile')
  const item = value as Record<string, unknown>
  if (typeof item.id !== 'string' || typeof item.published_node_id !== 'string' ||
      typeof item.joined_at !== 'string' || !Number.isFinite(Date.parse(item.joined_at)) ||
      item.display_name !== null && typeof item.display_name !== 'string' ||
      item.handle !== null && typeof item.handle !== 'string' ||
      item.bio !== null && typeof item.bio !== 'string') throw new ApiError(502, 'invalid_profile')
  return { id: item.id, published_node_id: item.published_node_id, joined_at: item.joined_at,
    display_name: item.display_name as string | null, handle: item.handle as string | null, bio: item.bio as string | null }
}

export function parseAccountProfile(value: unknown): AccountProfile {
  const item = value as AccountProfile | null
  if (!item || typeof item.id !== 'string' || !['free', 'pro', 'FREE', 'PRO'].includes(item.plan) ||
    !item.settings || !item.settings.learning || !item.learning_options || !Array.isArray(item.learning_options.pairs)) throw new ApiError(502, 'invalid_profile')
  return item
}

export async function fetchProfile(token: string, signal?: AbortSignal): Promise<AccountProfile> {
  const response = await fetch('/api/v1/me', {
    headers: { Authorization: `Bearer ${token}` }, cache: 'no-store', signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, typeof body?.error === 'string' ? body.error : 'request_failed')
  }
  return parseAccountProfile(await response.json())
}
