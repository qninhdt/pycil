import { webConfig } from '@/config'
import { parsePreparation, type Diagnostic, type PreparedQuestion, type PreparedSession, type ReviewBatchResult, type SubmittedResult } from '../../lib/api/study'

export type Attempt = { answer: string | null; answered_at: string; diagnostics: Diagnostic; complete: boolean }
export type StudySession = {
  version: 2; accountId: string; id: string; seed: string; prepared: PreparedSession
  round: number; questions: number[]; unseen: number[]; retry: number[]; position: number
  draft: string; pendingAttempt: { occurrence: number; answer: string | null; answered_at: string } | null
  attempts: Record<number, Attempt[]>; phase: 'question' | 'feedback' | 'recap' | 'submitting' | 'complete'
  submission: { key: string; results: SubmittedResult[] } | null
  receipt: ReviewBatchResult | null
  updated_at?: string
}

export const roundSize = webConfig.study.roundSize
export const sessionKey = (accountId: string, nodeId: string) => `pycil:study:${accountId}:${nodeId}`

export function loadSession(accountId: string, nodeId: string): StudySession | null {
  try {
    const raw = localStorage.getItem(sessionKey(accountId, nodeId))
    if (!raw) return null
    const value = JSON.parse(raw) as StudySession
    if (value?.version !== 2 || value.accountId !== accountId || value.prepared?.node_id !== nodeId) return null
    const prepared = parsePreparation(value.prepared)
    if (!prepared.actual_question_count || !['question', 'feedback', 'recap', 'submitting', 'complete'].includes(value.phase) ||
      typeof value.id !== 'string' || typeof value.seed !== 'string' || typeof value.draft !== 'string' ||
      !Number.isInteger(value.round) || value.round < 1 || !Number.isInteger(value.position) || value.position < 0 ||
      ![value.questions, value.unseen, value.retry].every(queue => Array.isArray(queue) && queue.every(index => Number.isInteger(index) && index >= 0 && index < prepared.actual_question_count)) ||
      !value.questions.length || value.position >= value.questions.length || !value.attempts || typeof value.attempts !== 'object' ||
      !Object.values(value.attempts).every(attempts => Array.isArray(attempts) && attempts.every(attempt => attempt && typeof attempt.complete === 'boolean' && attempt.diagnostics && typeof attempt.diagnostics === 'object'))) return null
    return { ...value, prepared }
  } catch { return null }
}

export function saveSession(value: StudySession) {
  localStorage.setItem(
    sessionKey(value.accountId, value.prepared.node_id),
    JSON.stringify({ ...value, updated_at: new Date().toISOString() })
  )
}

export function discardSession(accountId: string, nodeId: string) {
  try {
    localStorage.removeItem(sessionKey(accountId, nodeId))
  } catch {}
}

export function listActiveSessions(accountId: string): string[] {
  try {
    const prefix = `pycil:study:${accountId}:`
    const nodeIds: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) {
        nodeIds.push(key.slice(prefix.length))
      }
    }
    return nodeIds
  } catch { return [] }
}

export function pruneStaleSessions(accountId: string, maxAgeDays: number = webConfig.study.retentionDays) {
  try {
    const prefix = `pycil:study:${accountId}:`
    const now = Date.now()
    const maxAgeMs = maxAgeDays * 24 * 60 * 60 * 1000
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) {
        try {
          const raw = localStorage.getItem(key)
          if (!raw) continue
          const parsed = JSON.parse(raw) as StudySession
          if (parsed.updated_at && now - Date.parse(parsed.updated_at) > maxAgeMs) {
            localStorage.removeItem(key)
          }
        } catch {
          localStorage.removeItem(key)
        }
      }
    }
  } catch {}
}

export function allQuestions(session: StudySession): PreparedQuestion[] { return session.prepared.bundles.flatMap(bundle => bundle.questions) }
export function currentQuestion(session: StudySession): PreparedQuestion | null {
  return allQuestions(session)[session.questions[session.position]] ?? null
}
function hash(value: string) { let h = 2166136261; for (const ch of value) { h ^= ch.codePointAt(0)!; h = Math.imul(h, 16777619) } return h >>> 0 }
export function createStudySession(accountId: string, prepared: PreparedSession): StudySession {
  const seed = crypto.randomUUID(), occurrences = prepared.bundles.flatMap(bundle => bundle.questions).map((_, index) => index)
  occurrences.sort((a, b) => hash(`${seed}:${a}`) - hash(`${seed}:${b}`))
  return { version: 2, accountId, id: crypto.randomUUID(), seed, prepared, round: 1,
    questions: occurrences.slice(0, roundSize), unseen: occurrences.slice(roundSize), retry: [], position: 0, draft: '', pendingAttempt: null,
    attempts: {}, phase: 'question', submission: null, receipt: null, updated_at: new Date().toISOString() }
}
export function diagnosticComplete(diagnostic: Diagnostic): boolean {
  if ('correct' in diagnostic) return diagnostic.correct
  if ('task_fit' in diagnostic) return diagnostic.task_fit && !diagnostic.spelling_error && diagnostic.sense_id !== null
  if ('accuracy' in diagnostic) return diagnostic.sense_id !== null && diagnostic.accuracy === 'accurate' && diagnostic.coverage === 'sufficient'
  return diagnostic.used && diagnostic.meaning === 'correct' && diagnostic.form === 'correct' && diagnostic.construction === true &&
    diagnostic.collocation === true && diagnostic.appropriacy === true &&
    (!('meaning_preservation' in diagnostic) || diagnostic.meaning_preservation === 'preserved')
}
export function beginAttempt(session: StudySession, answer: string | null, now = new Date()): StudySession {
  if (session.phase !== 'question' || !currentQuestion(session)) throw new Error('The question is not ready for an answer.')
  if (session.pendingAttempt) return session
  if (answer !== null && !answer.trim()) throw new Error('Choose or enter an answer.')
  const occurrence = session.questions[session.position]
  if ((session.attempts[occurrence]?.length ?? 0) >= webConfig.study.maxAttempts) throw new Error('Attempt limit reached.')
  return { ...session, pendingAttempt: { occurrence, answer, answered_at: now.toISOString() } }
}
export function recordAttempt(session: StudySession, diagnostics: Diagnostic): StudySession {
  const pending = session.pendingAttempt
  if (session.phase !== 'question' || !pending || pending.occurrence !== session.questions[session.position]) throw new Error('Lock the answer before grading.')
  const complete = diagnosticComplete(diagnostics), attempts = [...(session.attempts[pending.occurrence] ?? []), { answer: pending.answer, answered_at: pending.answered_at, diagnostics, complete }]
  return { ...session, pendingAttempt: null, attempts: { ...session.attempts, [pending.occurrence]: attempts },
    retry: !complete && attempts.length < webConfig.study.maxAttempts ? [...session.retry, pending.occurrence] : session.retry, phase: 'feedback' }
}
export function completedCount(session: StudySession) {
  return allQuestions(session).filter((_, occurrence) => {
    const attempts = session.attempts[occurrence] ?? []
    return attempts.at(-1)?.complete || attempts.length === webConfig.study.maxAttempts
  }).length
}
export function finishSession(session: StudySession): StudySession {
  if (session.submission) return { ...session, phase: 'submitting' }
  const results: SubmittedResult[] = allQuestions(session).flatMap((item, occurrence) => {
    const initial = session.attempts[occurrence]?.[0]
    return initial ? [{ question_artifact_id: item.question.question_artifact_id, question_type: item.question.question_type,
      format: item.format, diagnostics: initial.diagnostics, answered_at: initial.answered_at }] : []
  })
  if (!results.length) throw new Error('Answer a question before saving results.')
  return { ...session, phase: 'submitting', submission: { key: crypto.randomUUID(), results } }
}
export function advanceSession(session: StudySession): StudySession {
  if (session.phase !== 'feedback') throw new Error('Finish the current answer first.')
  if (session.position + 1 < session.questions.length) return { ...session, position: session.position + 1, draft: '', phase: 'question' }
  if (!session.retry.length && !session.unseen.length) return finishSession(session)
  return { ...session, phase: 'recap' }
}
export function startNextRound(session: StudySession): StudySession {
  if (session.phase !== 'recap') throw new Error('Round is not complete.')
  const queue = [...session.retry, ...session.unseen], questions = queue.slice(0, roundSize)
  return { ...session, round: session.round + 1, questions, unseen: queue.slice(roundSize), retry: [], position: 0, draft: '', phase: 'question' }
}
