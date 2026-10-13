import { ApiError } from './error'

export type AccountProfile = {
  id: string
  display_name: string | null
  handle: string | null
  bio: string | null
  joined_at: string
  plan: 'free' | 'pro'
  personal_node_id: string
  published_node_id: string
  library_node_id: string
  learning_options: {
    pairs: { question_type: string; format: AnswerFormat; level: number }[]
    limits: { min_questions_per_sense: number; max_questions_per_sense: number; max_questions_per_prepare: number }
    advanced_grading: boolean
  }
  settings: { locale: string; timezone: string; translation_language: string; learning: LearningSettings; assistant: AssistantSettings }
  effective_learning: LearningSettings | null
  learning_restriction: string | null
}

export type AnswerFormat = 'single_choice' | 'single_word' | 'short_answer'
export type LearningSettings = {
  question_types: string[]; formats: AnswerFormat[]; questions_per_sense: number
  max_sense_count: number
}
export type AssistantSettings = { auto_approve: boolean }
export type SettingsPatch = { locale?: string; timezone?: string; translation_language?: string; learning?: Partial<LearningSettings>; assistant?: Partial<AssistantSettings> }
export type PublicProfile = Pick<AccountProfile, 'id' | 'display_name' | 'handle' | 'bio' | 'joined_at' | 'published_node_id'>
export type UsageAllowance = { period_start: string; period_end: string; allowance_units: number; used_units: number; remaining_units: number }

export function parseUsageAllowance(value: unknown): UsageAllowance {
  if (!value || typeof value !== 'object') throw new ApiError(502, 'invalid_response')
  const item = value as UsageAllowance
  if (![item.period_start, item.period_end].every(value => typeof value === 'string' && Number.isFinite(Date.parse(value))) ||
    Date.parse(item.period_end) <= Date.parse(item.period_start) ||
    ![item.allowance_units, item.used_units, item.remaining_units].every(value => Number.isSafeInteger(value) && value >= 0) ||
    item.remaining_units !== Math.max(0, item.allowance_units - item.used_units)) throw new ApiError(502, 'invalid_response')
  return { period_start: item.period_start, period_end: item.period_end, allowance_units: item.allowance_units, used_units: item.used_units, remaining_units: item.remaining_units }
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

const formats: AnswerFormat[] = ['single_choice', 'single_word', 'short_answer']
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ApiError(502, 'invalid_profile')
  return value as Record<string, unknown>
}
function text(value: unknown): string {
  if (typeof value !== 'string' || !value) throw new ApiError(502, 'invalid_profile')
  return value
}
function positive(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) throw new ApiError(502, 'invalid_profile')
  return value
}
function learning(value: unknown): LearningSettings {
  const item = record(value)
  if (!Array.isArray(item.question_types) || !item.question_types.length || !item.question_types.every(value => typeof value === 'string' && value.length > 0) ||
      !Array.isArray(item.formats) || !item.formats.length || !item.formats.every(value => formats.includes(value))) throw new ApiError(502, 'invalid_profile')
  return { question_types: item.question_types, formats: item.formats,
    questions_per_sense: positive(item.questions_per_sense), max_sense_count: positive(item.max_sense_count) }
}
export function parseAccountProfile(value: unknown): AccountProfile {
  const publicProfile = parsePublicProfile(value), item = record(value)
  const settings = record(item.settings), assistant = record(settings.assistant), options = record(item.learning_options), limits = record(options.limits)
  if (item.plan !== 'free' && item.plan !== 'pro' || typeof assistant.auto_approve !== 'boolean' || typeof options.advanced_grading !== 'boolean' ||
      !Array.isArray(options.pairs) || item.learning_restriction !== null && typeof item.learning_restriction !== 'string') throw new ApiError(502, 'invalid_profile')
  const timezone = text(settings.timezone)
  try { new Intl.DateTimeFormat('en', { timeZone: timezone }) } catch { throw new ApiError(502, 'invalid_profile') }
  const min = positive(limits.min_questions_per_sense), max = positive(limits.max_questions_per_sense), perPrepare = positive(limits.max_questions_per_prepare)
  if (min > max || max > perPrepare) throw new ApiError(502, 'invalid_profile')
  return { ...publicProfile, plan: item.plan, personal_node_id: text(item.personal_node_id), library_node_id: text(item.library_node_id),
    settings: { locale: text(settings.locale), timezone, translation_language: text(settings.translation_language), learning: learning(settings.learning), assistant: { auto_approve: assistant.auto_approve } },
    learning_options: { advanced_grading: options.advanced_grading,
      limits: { min_questions_per_sense: min, max_questions_per_sense: max, max_questions_per_prepare: perPrepare },
      pairs: options.pairs.map(value => {
        const pair = record(value)
        if (!formats.includes(pair.format as AnswerFormat)) throw new ApiError(502, 'invalid_profile')
        const level = positive(pair.level)
        if (level > 5) throw new ApiError(502, 'invalid_profile')
        return { question_type: text(pair.question_type), format: pair.format as AnswerFormat, level }
      }) },
    effective_learning: item.effective_learning === null ? null : learning(item.effective_learning), learning_restriction: item.learning_restriction as string | null,
  }
}
