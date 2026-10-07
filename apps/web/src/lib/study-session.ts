import type { GradeResult, PreparedQuestion, PreparedSession, Rating, ReviewBatchResult } from './home-api'

export type Outcome = 'clear' | 'partial' | 'miss'
export type Attempt = { answer: string; outcome: Outcome; grade: GradeResult | null }
export type StudySession = {
  version: 1; accountId: string; id: string; seed: string; prepared: PreparedSession
  round: number; questions: number[]; unseen: number[]; retry: number[]; position: number
  draft: string
  attempts: Record<number, Attempt[]>; phase: 'question' | 'feedback' | 'recap' | 'submitting' | 'complete'
  submission: { key: string; results: { sense_id: number; rating: Rating }[] } | null
  receipt: ReviewBatchResult | null
}

export const roundSize = 8
export const sessionKey = (accountId: string) => `pycil:study:${accountId}`
export function loadSession(accountId: string): StudySession | null {
  try {
    const raw = localStorage.getItem(sessionKey(accountId))
    if (!raw) return null
    const value = JSON.parse(raw) as StudySession
    return value.version === 1 && value.accountId === accountId && Array.isArray(value.prepared?.bundles) && Array.isArray(value.questions) ? value : null
  } catch { return null }
}
export function saveSession(value: StudySession) { localStorage.setItem(sessionKey(value.accountId), JSON.stringify(value)) }
export function discardSession(accountId: string) { localStorage.removeItem(sessionKey(accountId)) }
export function allQuestions(session: StudySession): PreparedQuestion[] { return session.prepared.bundles.flatMap(bundle => bundle.questions) }
export function currentQuestion(session: StudySession): PreparedQuestion | null {
  const id = session.questions[session.position]
  return allQuestions(session).find(item => item.question.id === id) ?? null
}
function hash(value: string) { let h = 2166136261; for (const ch of value) { h ^= ch.codePointAt(0)!; h = Math.imul(h, 16777619) } return h >>> 0 }
export function createStudySession(accountId: string, prepared: PreparedSession): StudySession {
  const seed = crypto.randomUUID(), ids = prepared.bundles.flatMap(bundle => bundle.questions.map(item => item.question.id))
  ids.sort((a, b) => hash(`${seed}:${a}`) - hash(`${seed}:${b}`))
  return { version: 1, accountId, id: crypto.randomUUID(), seed, prepared, round: 1,
    questions: ids.slice(0, roundSize), unseen: ids.slice(roundSize), retry: [], position: 0, draft: '',
    attempts: {}, phase: 'question', submission: null, receipt: null }
}
export function gradeOutcome(item: PreparedQuestion, answer: string, grade: GradeResult | null): Outcome {
  if (item.format === 'SINGLE_CHOICE') return answer === item.question.correct.id ? 'clear' : 'miss'
  if (!grade) throw new Error('A typed answer needs a grade.')
  if ('task_fit' in grade) return grade.task_fit && !grade.spelling_error && grade.sense_id === item.question.sense_id ? 'clear'
    : grade.task_fit && grade.spelling_error ? 'partial' : 'miss'
  if ('accuracy' in grade) return grade.sense_id === item.question.sense_id && grade.accuracy === 'ACCURATE' && grade.coverage === 'SUFFICIENT' ? 'clear'
    : grade.sense_id === item.question.sense_id && ['ACCURATE', 'MIXED'].includes(grade.accuracy ?? '') && ['SUFFICIENT', 'PARTIAL'].includes(grade.coverage ?? '') ? 'partial' : 'miss'
  if (!grade.used || !grade.meaning || !grade.form || grade.meaning === 'WRONG' || grade.form === 'FORM_ERROR' || grade.construction !== true || !grade.collocation || !grade.appropriacy || grade.appropriacy === 'INAPPROPRIATE') return 'miss'
  return grade.meaning === 'CORRECT' && grade.form === 'CORRECT' && grade.construction === true &&
    (grade.collocation === 'NATURAL' || grade.collocation === 'ACCEPTABLE') && grade.appropriacy === 'APPROPRIATE' ? 'clear' : 'partial'
}
export function recordAttempt(session: StudySession, answer: string, grade: GradeResult | null, unknown = false): StudySession {
  if (session.phase !== 'question') throw new Error('The question is not ready for an answer.')
  const item = currentQuestion(session)
  if (!item || !answer.trim() && !unknown) throw new Error('Choose or enter an answer.')
  const outcome = unknown ? 'miss' : gradeOutcome(item, answer, grade)
  const attempts = [...(session.attempts[item.question.id] ?? []), { answer, grade, outcome }]
  if (attempts.length > 3) throw new Error('Attempt limit reached.')
  return { ...session, attempts: { ...session.attempts, [item.question.id]: attempts },
    retry: outcome !== 'clear' && attempts.length < 3 ? [...session.retry, item.question.id] : session.retry, phase: 'feedback' }
}
export function completedCount(session: StudySession) {
  return allQuestions(session).filter(item => {
    const attempts = session.attempts[item.question.id] ?? []
    return attempts.at(-1)?.outcome === 'clear' || attempts.length === 3
  }).length
}
export function advanceSession(session: StudySession): StudySession {
  if (session.phase !== 'feedback') throw new Error('Finish the current answer first.')
  if (session.position + 1 < session.questions.length) return { ...session, position: session.position + 1, draft: '', phase: 'question' }
  if (!session.retry.length && !session.unseen.length) return { ...session, phase: 'submitting', submission: {
    key: crypto.randomUUID(), results: session.prepared.bundles.map(bundle => ({ sense_id: bundle.sense.id, rating: ratingForSense(session, bundle.sense.id) })) } }
  return { ...session, phase: 'recap' }
}
export function startNextRound(session: StudySession): StudySession {
  if (session.phase !== 'recap') throw new Error('Round is not complete.')
  const questions = [...session.retry, ...session.unseen].slice(0, roundSize)
  return { ...session, round: session.round + 1, questions, unseen: session.unseen.slice(Math.max(0, roundSize - session.retry.length)),
    retry: [], position: 0, draft: '', phase: 'question' }
}
export function ratingForSense(session: StudySession, senseId: number): Rating {
  const bundle = session.prepared.bundles.find(item => item.sense.id === senseId)
  if (!bundle) throw new Error('Sense is missing from the session.')
  const histories = bundle.questions.map(item => session.attempts[item.question.id] ?? [])
  if (histories.some(history => !history.length)) throw new Error('Sense has unfinished questions.')
  const initialMisses = histories.filter(history => history[0].outcome === 'miss').length
  const final = histories.map(history => history.at(-1)!.outcome)
  if (final.includes('miss') || !final.includes('clear') || histories.length >= 2 && initialMisses > histories.length / 2) return 'AGAIN'
  if (histories.some(history => history.some(attempt => attempt.outcome !== 'clear'))) return 'HARD'
  if (histories.length >= 2 && (new Set(bundle.questions.map(item => item.question.question_type)).size >= 2 || bundle.questions.some(item => item.level >= 3))) return 'EASY'
  return 'GOOD'
}
