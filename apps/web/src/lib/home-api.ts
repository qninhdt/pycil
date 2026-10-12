import { shiftDay } from './home-calendar'
import { parseDictionarySense, type DictionarySense } from './dictionary-model'
import type { AnswerFormat, LearningSettings } from './api'

export type StudySummary = {
  node_id: string; as_of: string; total: number; new: number; studied: number
  due: number; not_due: number; last_studied_at: string | null; reachable_decks: number
}
export type ActivityDay = { day: string; applied_events: number; practice_events: number }
export type StudyActivity = {
  as_of: string; timezone: string; start_date: string; end_date: string; days: ActivityDay[]
  current_streak: number; longest_streak: number; applied_events: number; practice_events: number
}
export type ReviewSchedule = {
  node_id: string; as_of: string; timezone: string; start_date: string; end_date: string
  days: { day: string; count: number }[]
}
export type LibraryNode = {
  id: string; name: string; type: 'FOLDER' | 'DECK' | 'REFERENCE'
  description: string | null; summary: StudySummary | null
  owner_id?: string
  reference_id?: string | null; target_type?: 'DECK' | 'FOLDER' | null
}
export type LibraryPage = { nodes: LibraryNode[]; next_cursor: string | null }
export type SessionSelection = 'DUE' | 'NEW' | 'AUTO'
export type QuestionType = 'DEFINITION_TO_WORD' | 'CONTEXT_TO_WORD' | 'CLOZE_TO_WORD' | 'WORD_TO_DEFINITION' | 'WORD_TO_USAGE' | 'DIALOGUE_COMPLETION' | 'MEANING_IN_CONTEXT' | 'SENTENCE_REWRITE'
export type QuestionOption = { id: string; content: string }
export type StudyQuestion = { question_artifact_id: number; sense_id: number; question_type: QuestionType; content: string | { speaker: string; text: string | null }[]; correct: QuestionOption; distractors: QuestionOption[]; target_placement: 'DIALOGUE' | 'OPTIONS' | null }
export type PreparedQuestion = { question: StudyQuestion; format: AnswerFormat; level: number; options: QuestionOption[] }
export type PreparedBundle = { sense: DictionarySense; reason: 'DUE' | 'NEW' | 'NOT_YET_DUE'; questions: PreparedQuestion[] }
export type PreparedSession = { node_id: string; selection: SessionSelection; max_sense_count: number; actual_sense_count: number; actual_question_count: number; preferences: LearningSettings; bundles: PreparedBundle[] }
export type QuizDiagnostic = { correct: boolean }
export type SingleWordDiagnostic = { task_fit: boolean; spelling_error: boolean; sense_id: number | null }
export type DefinitionDiagnostic = { sense_id: number | null; accuracy: 'ACCURATE' | 'MIXED' | 'INACCURATE' | null; coverage: 'SUFFICIENT' | 'PARTIAL' | 'MINIMAL' | null }
export type UsageDiagnostic = { used: boolean; meaning: 'CORRECT' | 'APPROXIMATE' | 'WRONG' | null; form: 'CORRECT' | 'SPELLING_ERROR' | 'FORM_ERROR' | null; construction: boolean | null; collocation: boolean | null; appropriacy: boolean | null }
export type RewriteDiagnostic = UsageDiagnostic & { meaning_preservation: 'PRESERVED' | 'PARTIAL' | 'CHANGED' | null }
export type Diagnostic = QuizDiagnostic | SingleWordDiagnostic | DefinitionDiagnostic | UsageDiagnostic | RewriteDiagnostic
export type QuestionReference = { question_artifact_id: number; question_type: QuestionType; format: AnswerFormat }
export type GradeInput = QuestionReference & { answer: string | null }
export type GradeResult = QuestionReference & { diagnostics: Diagnostic }
export type SubmittedResult = GradeResult & { answered_at: string }
export type TrackedEvidence = SubmittedResult & { evaluated_sense_id: number; recall: number | null; performance: number | null; opponent_elo: number; policy_version: number }
export type ReviewBatchResult = { accepted_at: string; activity_day: string; results: { sense_id: number; applied: boolean; elo: number; level: number; stability: number; difficulty: number; last_exposure_at: string; due_after: string }[]; evidence: TrackedEvidence[] }
const questionTypes: QuestionType[] = ['DEFINITION_TO_WORD','CONTEXT_TO_WORD','CLOZE_TO_WORD','WORD_TO_DEFINITION','WORD_TO_USAGE','DIALOGUE_COMPLETION','MEANING_IN_CONTEXT','SENTENCE_REWRITE']
const answerFormats: AnswerFormat[] = ['SINGLE_CHOICE','SINGLE_WORD','SHORT_ANSWER']

export class HomeApiError extends Error {
  constructor(public status: number, public code: string) {
    super(status === 401 ? 'Your session has expired. Sign in again.'
      : code === 'scope_too_large' ? 'This Library is too large to calculate at once. Open a smaller folder or deck.'
      : code === 'reference_unavailable' ? 'This reference is no longer available.'
      : code === 'question_generation_unavailable' ? 'Questions could not be generated right now. Retry to prepare your session.'
      : code === 'grading_unavailable' ? 'Your answer could not be checked right now. Retry without changing your answer.'
      : code === 'node_not_found' ? 'This material could not be found.'
      : code === 'invalid_cursor' ? 'This page is no longer available. Return to the first page.'
      : code === 'handle_unavailable' ? 'This handle is already taken. Choose another handle.'
      : code === 'invalid_handle' ? 'Use 3–30 lowercase letters, numbers or underscores, starting with a letter.'
      : code === 'node_cycle' ? 'Choose a destination outside this folder and its contents.'
      : code === 'quota_exceeded' || code === 'deck_sense_limit_exceeded' ? 'This change exceeds your Library limit. Remove some material or choose a smaller selection.'
      : code === 'publication_confirmation_required' ? 'Confirm that this material will be publicly readable.'
      : code === 'private_reference_cannot_be_published' ? 'This material references a private source. Publish the source or remove that reference first.'
      : status === 429 ? 'Too many requests. Wait a moment, then retry.'
      : code === 'invalid_response' ? 'The server returned incomplete data. Please retry.'
      : status === 422 ? 'This selection could not be prepared. Check your learning settings or choose a smaller scope.'
      : 'Could not load this information. Check your connection and retry.')
  }
}

type RecordValue = Record<string, unknown>
function record(value: unknown): RecordValue {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new HomeApiError(502, 'invalid_response')
  return value as RecordValue
}
function text(value: unknown): string {
  if (typeof value !== 'string' || !value) throw new HomeApiError(502, 'invalid_response')
  return value
}
function count(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new HomeApiError(502, 'invalid_response')
  return value
}
function date(value: unknown): string {
  const result = text(value)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || !Number.isFinite(Date.parse(`${result}T00:00:00Z`)) || new Date(`${result}T00:00:00Z`).toISOString().slice(0, 10) !== result) throw new HomeApiError(502, 'invalid_response')
  return result
}
function timestamp(value: unknown): string {
  const result = text(value)
  if (!Number.isFinite(Date.parse(result))) throw new HomeApiError(502, 'invalid_response')
  return result
}
function list(value: unknown): unknown[] {
  if (!Array.isArray(value)) throw new HomeApiError(502, 'invalid_response')
  return value
}
function positive(value: unknown): number { const result = count(value); if (!result) throw new HomeApiError(502, 'invalid_response'); return result }
function nullablePositive(value: unknown): number | null { return value === null ? null : positive(value) }
function nullableChoice<T extends string>(value: unknown, choices: readonly T[]): T | null {
  if (value === null) return null
  if (typeof value !== 'string' || !choices.includes(value as T)) throw new HomeApiError(502, 'invalid_response')
  return value as T
}
function option(value: unknown): QuestionOption { const item = record(value); return { id: text(item.id), content: text(item.content) } }
function preparedQuestion(value: unknown): PreparedQuestion {
  const item = record(value), question = record(item.question), kind = text(question.question_type), format = text(item.format)
  if (!questionTypes.includes(kind as QuestionType) || !answerFormats.includes(format as AnswerFormat)) throw new HomeApiError(502, 'invalid_response')
  const correct = option(question.correct), distractors = list(question.distractors).map(option), options = list(item.options).map(option)
  if (options.length !== distractors.length + 1 || new Set(options.map(value => value.id)).size !== options.length ||
    new Set([correct.id, ...distractors.map(value => value.id)]).size !== options.length ||
    options.some(value => ![correct.id, ...distractors.map(item => item.id)].includes(value.id))) throw new HomeApiError(502, 'invalid_response')
  const content = typeof question.content === 'string' ? question.content : list(question.content).map(value => {
    const turn = record(value)
    return { speaker: text(turn.speaker), text: turn.text === null ? null : text(turn.text) }
  })
  const placement = question.target_placement === null ? null : text(question.target_placement)
  if (placement !== null && placement !== 'DIALOGUE' && placement !== 'OPTIONS') throw new HomeApiError(502, 'invalid_response')
  return { question: { question_artifact_id: positive(question.question_artifact_id), sense_id: positive(question.sense_id),
    question_type: kind as QuestionType, content, correct, distractors,
    target_placement: placement }, format: format as AnswerFormat, level: positive(item.level), options }
}

export function parseSummary(value: unknown): StudySummary {
  const item = record(value)
  const result = {
    node_id: text(item.node_id), as_of: timestamp(item.as_of), total: count(item.total),
    new: count(item.new), studied: count(item.studied), due: count(item.due), not_due: count(item.not_due),
    last_studied_at: item.last_studied_at === null ? null : timestamp(item.last_studied_at), reachable_decks: count(item.reachable_decks),
  }
  if (result.total !== result.new + result.studied || result.studied !== result.due + result.not_due) throw new HomeApiError(502, 'invalid_response')
  return result
}

function reporting(value: unknown) {
  const item = record(value)
  const timezone = text(item.timezone)
  try { new Intl.DateTimeFormat('en', { timeZone: timezone }) } catch { throw new HomeApiError(502, 'invalid_response') }
  return { item, as_of: timestamp(item.as_of), timezone, start_date: date(item.start_date), end_date: date(item.end_date) }
}

function completeWindow(start: string, end: string, days: { day: string }[]) {
  const length = Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86400000) + 1
  if (length < 1 || length > 1000 || days.length !== length || days.some((day, index) => day.day !== shiftDay(start, index))) throw new HomeApiError(502, 'invalid_response')
}

export function parseActivity(value: unknown): StudyActivity {
  const { item, ...period } = reporting(value)
  const result = { ...period, current_streak: count(item.current_streak), longest_streak: count(item.longest_streak),
    applied_events: count(item.applied_events), practice_events: count(item.practice_events),
    days: list(item.days).map(value => {
      const day = record(value)
      return { day: date(day.day), applied_events: count(day.applied_events), practice_events: count(day.practice_events) }
    }) }
  completeWindow(result.start_date, result.end_date, result.days)
  if (result.current_streak > result.longest_streak || result.applied_events !== result.days.reduce((sum, day) => sum + day.applied_events, 0) || result.practice_events !== result.days.reduce((sum, day) => sum + day.practice_events, 0)) throw new HomeApiError(502, 'invalid_response')
  return result
}

export function parseSchedule(value: unknown): ReviewSchedule {
  const { item, ...period } = reporting(value)
  const result = { ...period, node_id: text(item.node_id), days: list(item.days).map(value => {
    const day = record(value)
    return { day: date(day.day), count: count(day.count) }
  }) }
  completeWindow(result.start_date, result.end_date, result.days)
  return result
}

export function parseLibrary(value: unknown): LibraryPage {
  const item = record(value)
  return { next_cursor: item.next_cursor === null ? null : text(item.next_cursor), nodes: list(item.nodes).map(value => {
    const node = record(value)
    if (!['FOLDER', 'DECK', 'REFERENCE'].includes(text(node.type))) throw new HomeApiError(502, 'invalid_response')
    if (node.target_type != null && !['DECK', 'FOLDER'].includes(text(node.target_type))) throw new HomeApiError(502, 'invalid_response')
    return { id: text(node.id), name: text(node.name), type: node.type as LibraryNode['type'], owner_id: node.owner_id == null ? undefined : text(node.owner_id),
      description: node.description === null ? null : text(node.description), summary: node.summary == null ? null : parseSummary(node.summary),
      reference_id: node.reference_id == null ? null : text(node.reference_id), target_type: node.target_type as LibraryNode['target_type'] ?? null }
  }) }
}

export function parsePreparation(value: unknown): PreparedSession {
  const item = record(value)
  if (!['DUE', 'NEW', 'AUTO'].includes(text(item.selection))) throw new HomeApiError(502, 'invalid_response')
  const preferences = record(item.preferences), bundles = list(item.bundles).map(value => {
    const bundle = record(value), sense = parseDictionarySense(bundle.sense), reason = text(bundle.reason)
    if (!['DUE','NEW','NOT_YET_DUE'].includes(reason)) throw new HomeApiError(502, 'invalid_response')
    const questions = list(bundle.questions).map(preparedQuestion)
    if (questions.some(value => value.question.sense_id !== sense.id)) throw new HomeApiError(502, 'invalid_response')
    return { sense, reason: reason as PreparedBundle['reason'], questions }
  })
  const settings: LearningSettings = { question_types: list(preferences.question_types).map(value => {
    const kind = text(value); if (!questionTypes.includes(kind as QuestionType)) throw new HomeApiError(502, 'invalid_response'); return kind
  }), formats: list(preferences.formats).map(value => {
    const format = text(value); if (!answerFormats.includes(format as AnswerFormat)) throw new HomeApiError(502, 'invalid_response'); return format as AnswerFormat
  }),
    questions_per_sense: positive(preferences.questions_per_sense), max_sense_count: positive(preferences.max_sense_count) }
  const result = { node_id: text(item.node_id), selection: item.selection as SessionSelection, max_sense_count: positive(item.max_sense_count),
    actual_sense_count: count(item.actual_sense_count), actual_question_count: count(item.actual_question_count), preferences: settings, bundles }
  const questions = bundles.flatMap(bundle => bundle.questions)
  if (result.actual_sense_count !== bundles.length || result.actual_question_count !== questions.length ||
    result.actual_question_count > 60 || result.max_sense_count > 20 || settings.questions_per_sense > 3 || result.actual_sense_count > result.max_sense_count ||
    new Set(bundles.map(bundle => bundle.sense.id)).size !== bundles.length || bundles.some(bundle => bundle.questions.length !== settings.questions_per_sense) ||
    questions.some(value => value.level > 5)) throw new HomeApiError(502, 'invalid_response')
  return result
}
function bool(value: unknown): boolean {
  if (typeof value !== 'boolean') throw new HomeApiError(502, 'invalid_response')
  return value
}
function nullableBool(value: unknown): boolean | null { return value === null ? null : bool(value) }
function finite(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new HomeApiError(502, 'invalid_response')
  return value
}
function score(value: unknown): number | null {
  if (value === null) return null
  const result = finite(value)
  if (result < 0 || result > 1) throw new HomeApiError(502, 'invalid_response')
  return result
}
export function parseGrade(value: unknown): GradeResult {
  const item = record(value), kind = text(item.question_type), format = text(item.format), diag = record(item.diagnostics)
  if (!questionTypes.includes(kind as QuestionType) || !answerFormats.includes(format as AnswerFormat)) throw new HomeApiError(502, 'invalid_response')
  let diagnostics: Diagnostic
  if (format === 'SINGLE_CHOICE') diagnostics = { correct: bool(diag.correct) }
  else if (format === 'SINGLE_WORD') diagnostics = { task_fit: bool(diag.task_fit), spelling_error: bool(diag.spelling_error), sense_id: nullablePositive(diag.sense_id) }
  else if (kind === 'WORD_TO_DEFINITION') {
    const sense_id = nullablePositive(diag.sense_id), accuracy = nullableChoice(diag.accuracy, ['ACCURATE','MIXED','INACCURATE']), coverage = nullableChoice(diag.coverage, ['SUFFICIENT','PARTIAL','MINIMAL'])
    if (sense_id === null ? accuracy !== null || coverage !== null : accuracy === null || coverage === null) throw new HomeApiError(502, 'invalid_response')
    diagnostics = { sense_id, accuracy, coverage }
  } else {
    const usage: UsageDiagnostic = { used: bool(diag.used), meaning: nullableChoice(diag.meaning, ['CORRECT','APPROXIMATE','WRONG']), form: nullableChoice(diag.form, ['CORRECT','SPELLING_ERROR','FORM_ERROR']), construction: nullableBool(diag.construction), collocation: nullableBool(diag.collocation), appropriacy: nullableBool(diag.appropriacy) }
    const components = [usage.meaning, usage.form, usage.construction, usage.collocation, usage.appropriacy]
    if (usage.used ? components.some(value => value === null) : components.some(value => value !== null)) throw new HomeApiError(502, 'invalid_response')
    diagnostics = usage
    if (kind === 'SENTENCE_REWRITE') {
      const meaning_preservation = nullableChoice(diag.meaning_preservation, ['PRESERVED','PARTIAL','CHANGED'])
      if (usage.used === (meaning_preservation === null)) throw new HomeApiError(502, 'invalid_response')
      diagnostics = { ...usage, meaning_preservation }
    }
  }
  return { question_artifact_id: positive(item.question_artifact_id), question_type: kind as QuestionType, format: format as AnswerFormat, diagnostics }
}
export function parseReviewBatch(value: unknown): ReviewBatchResult {
  const item = record(value)
  return { accepted_at: timestamp(item.accepted_at), activity_day: date(item.activity_day), results: list(item.results).map(value => {
    const row = record(value), level = positive(row.level), stability = finite(row.stability), difficulty = finite(row.difficulty)
    if (level > 5 || stability <= 0 || difficulty < 1 || difficulty > 10) throw new HomeApiError(502, 'invalid_response')
    return { sense_id: positive(row.sense_id), applied: bool(row.applied), elo: finite(row.elo), level, stability, difficulty, last_exposure_at: timestamp(row.last_exposure_at), due_after: timestamp(row.due_after) }
  }), evidence: list(item.evidence).map(value => {
    const row = record(value)
    return { ...parseGrade(row), answered_at: timestamp(row.answered_at), evaluated_sense_id: positive(row.evaluated_sense_id), recall: score(row.recall), performance: score(row.performance), opponent_elo: finite(row.opponent_elo), policy_version: positive(row.policy_version) }
  }) }
}

export async function homeRequest<T>(path: string, token: string | null, parse: (value: unknown) => T, signal: AbortSignal, body?: unknown, method?: 'POST' | 'PATCH' | 'DELETE', extraHeaders?: Record<string, string>): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'), cache: 'no-store', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const value: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new HomeApiError(response.status, value && typeof value === 'object' && 'error' in value && typeof value.error === 'string' ? value.error : 'request_failed')
  const params = new URLSearchParams(path.split('?')[1])
  if (params.has('start_date') && (record(value).start_date !== params.get('start_date') || record(value).end_date !== params.get('end_date'))) throw new HomeApiError(502, 'invalid_response')
  return parse(value)
}

export async function homeToken(getToken: () => Promise<string | null>, signal: AbortSignal): Promise<string> {
  let abort: () => void = () => {}
  try {
    const token = await Promise.race([getToken(), new Promise<never>((_, reject) => {
      abort = () => reject(signal.reason ?? new Error('Request cancelled.'))
      if (signal.aborted) abort()
      else signal.addEventListener('abort', abort, { once: true })
    })])
    if (!token) throw new HomeApiError(401, 'authentication_required')
    return token
  } finally { signal.removeEventListener('abort', abort) }
}
