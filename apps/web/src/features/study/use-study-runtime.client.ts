'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useAccount } from '@/features/account/account.client'
import { useServices } from '@/lib/api/services/provider.client'
import { ApiError } from '@/lib/api/error'
import { resumeJob } from '@/lib/api/jobs'
import { parsePreparation } from '@/lib/api/study'
import { studyReturnHref } from './navigation'
import { advanceSession, beginAttempt, completedCount, createStudySession, currentQuestion, discardSession, loadSession, pruneStaleSessions, recordAttempt, saveSession, sessionKey, type StudySession } from './session'
import type { Diagnostic, SessionSelection } from '@/lib/api/study'

export function useStudyRuntime(initialSession?: StudySession) {
  const router = useRouter()
  const account = useAccount(),
    { services, scope } = useServices(),
    params = useSearchParams()
  const queryClient = useQueryClient()
  const t = useTranslations('learning')
  const profile = account.profile,
    accountId = profile?.id ?? ''
  const nodeId = params?.get('node') || profile?.library_node_id || ''
  const selection = (
    params?.get('selection') === 'new' || params?.get('selection') === 'due' ? params?.get('selection') : 'auto'
  ) as SessionSelection
  const backHref = studyReturnHref(nodeId, profile, params?.get('owner'))
  const [session, setSession] = useState<StudySession | null>(initialSession ?? null)
  const [hydrated, setHydrated] = useState(Boolean(initialSession)),
    [starting, setStarting] = useState(false),
    [busy, setBusy] = useState(false)
  const [error, setError] = useState(''),
    [submitError, setSubmitError] = useState(''),
    [blocked, setBlocked] = useState(false)
  const [selected, setSelected] = useState('')
  const [names, setNames] = useState<Record<number, string>>({})
  const [exitDialogOpen, setExitDialogOpen] = useState(false)
  const preparation = useRef<AbortController | null>(null)
  const submitting = useRef(false)
  const lastSaved = useRef<string | null>(initialSession ? 'mock-saved' : null)
  const prepared = session?.prepared

  useEffect(() => {
    if (initialSession) {
      setSession(initialSession)
      setBlocked(false)
      setHydrated(true)
      return
    }
    if (!accountId || !nodeId) return
    pruneStaleSessions(accountId)
    try {
      lastSaved.current = localStorage.getItem(sessionKey(accountId, nodeId))
    } catch {
      setError(t('storageError'))
      setHydrated(true)
      return
    }
    const existing = loadSession(accountId, nodeId)
    if (existing && existing.phase !== 'complete') {
      setSession(existing)
    } else {
      if (existing?.phase === 'complete') {
        discardSession(accountId, nodeId)
        lastSaved.current = null
      }
      setSession(null)
    }
    setBlocked(false)
    setError('')
    setHydrated(true)
  }, [accountId, nodeId, initialSession, t])

  const commit = useCallback(
    (next: StudySession) => {
      try {
        if (!initialSession) {
          if (localStorage.getItem(sessionKey(next.accountId, next.prepared.node_id)) !== lastSaved.current) {
            setError(t('sessionConflictError'))
            return false
          }
          saveSession(next)
          lastSaved.current = localStorage.getItem(sessionKey(next.accountId, next.prepared.node_id))
        }
        setSession(next)
        setError('')
        return true
      } catch {
        setError(t('storageError'))
        return false
      }
    },
    [initialSession, t]
  )

  useEffect(() => {
    if (!prepared || !services.dictionary.previews) return
    const ids = [...new Set(prepared.bundles.map(bundle => bundle.sense.word_id))]
    const controller = new AbortController()
    Promise.all(
      Array.from({ length: Math.ceil(ids.length / 30) }, (_, index) =>
        services.dictionary.previews(ids.slice(index * 30, index * 30 + 30), controller.signal)
      )
    )
      .then(groups => setNames(Object.fromEntries(groups.flat().map(word => [word.word_id, word.lemma]))))
      .catch(() => {})
    return () => controller.abort()
  }, [prepared, services.dictionary])

  useEffect(() => () => preparation.current?.abort(), [accountId, nodeId, selection])

  const start = useCallback(async () => {
    if (!account.canMutate || !profile || starting || preparation.current || !nodeId) return
    const controller = new AbortController()
    preparation.current = controller
    setStarting(true)
    setError('')
    setBlocked(false)
    try {
      const prepared = await resumeJob(
        queryClient,
        `pycil:study-job:${profile.id}:${nodeId}:${selection}:${JSON.stringify(profile.effective_learning)}`,
        () => services.learning.prepare({ node_id: nodeId, selection }, controller.signal),
        services.jobs.status, parsePreparation, controller.signal,
      )
      if (controller.signal.aborted) return
      if (!prepared.bundles.length) {
        setError(t('noEligibleQuestions'))
        return
      }
      commit(createStudySession(profile.id, prepared))
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : t('couldNotPrepareSession'))
    } finally {
      if (preparation.current === controller) {
        preparation.current = null
        setStarting(false)
      }
    }
  }, [account.canMutate, profile, starting, nodeId, services.learning, services.jobs, queryClient, selection, commit, t])

  useEffect(() => {
    if (!hydrated || initialSession || session || starting || !profile || !nodeId || error) return
    void start()
  }, [hydrated, initialSession, session, starting, profile, nodeId, error, account.canMutate, start])

  const item = session ? currentQuestion(session) : null
  const phase = session?.phase
  const typed = session?.draft ?? ''
  const question = item?.question
  const occurrence = session?.questions[session.position]
  const attempt = occurrence === undefined ? null : session?.attempts[occurrence]?.at(-1)
  const total = session?.prepared.actual_question_count ?? 0
  const finished = session ? completedCount(session) : 0
  const selectedOption = item?.options.find(opt => opt.id === selected)

  const answer = useCallback(async (value: string, unknown = false) => {
    if (!session || !item || busy || blocked) return
    if (!initialSession && localStorage.getItem(sessionKey(accountId, session.prepared.node_id)) !== lastSaved.current) {
      setError(t('sessionConflictError'))
      return
    }
    if (!session.pendingAttempt && !value.trim() && !unknown) {
      setError(t('chooseOrEnterAnswer'))
      return
    }
    setBusy(true)
    setError('')
    try {
      const locked = beginAttempt(session, unknown ? null : value)
      if (!commit(locked)) return
      const pending = locked.pendingAttempt!
      let diagnostics: Diagnostic
      if (item.format === 'single_choice') {
        if (pending.answer !== null && !item.options.some(option => option.id === pending.answer)) throw new Error(t('chooseAvailableAnswer'))
        diagnostics = { correct: pending.answer === item.question.correct.id }
      } else {
        const grade = await services.learning.grade({ question_artifact_id: item.question.question_artifact_id,
          question_type: item.question.question_type, format: item.format, answer: pending.answer }, new AbortController().signal)
        if (grade.question_artifact_id !== item.question.question_artifact_id || grade.question_type !== item.question.question_type || grade.format !== item.format) throw new ApiError(502, 'invalid_response')
        diagnostics = grade.diagnostics
      }
      commit(recordAttempt(locked, diagnostics))
    } catch (cause) {
      if (
        cause instanceof ApiError &&
        (cause.code === 'advanced_grading_not_available' ||
          cause.code === 'question_artifact_not_found' ||
          cause.code === 'unsupported_question_format')
      ) {
        setBlocked(true)
        setError(t('gradingUnavailable'))
      } else setError(cause instanceof Error ? cause.message : t('couldNotCheckAnswer'))
    } finally {
      setBusy(false)
    }
  }, [session, item, busy, blocked, initialSession, accountId, services.learning, commit, t])

  const next = useCallback(() => {
    if (!session) return
    if (commit(advanceSession(session))) setSelected('')
  }, [session, commit])

  const submit = useCallback(
    async (current: StudySession) => {
      if (!current.submission || submitting.current) return
      submitting.current = true
      setSubmitError('')
      try {
        const receipt = await services.learning.review(current.submission, new AbortController().signal)
        if (receipt.evidence.length !== current.submission.results.length || receipt.evidence.some((result, index) => {
          const expected = current.submission!.results[index]
          return result.question_artifact_id !== expected.question_artifact_id || result.question_type !== expected.question_type || result.format !== expected.format || Date.parse(result.answered_at) !== Date.parse(expected.answered_at)
        })) throw new ApiError(502, 'invalid_response')
        if (!commit({ ...current, receipt, phase: 'complete' }))
          setSubmitError(t('resultsAcceptedStorageError'))
        await Promise.all([
          invalidateLibrary(queryClient, services.mode, scope),
          queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'activity'] }),
          queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'usage'] }),
        ])
      } catch (cause) {
        setSubmitError(cause instanceof Error ? cause.message : t('resultsNotConfirmed'))
      } finally {
        submitting.current = false
      }
    },
    [commit, services.learning, services.mode, scope, queryClient, t]
  )

  useEffect(() => {
    if (session?.phase === 'submitting' && !session.receipt) void submit(session)
  }, [session, submit])

  // Instant keyboard submission on 1-4 for SINGLE_CHOICE
  useEffect(() => {
    if (phase !== 'question' || !item || item.format !== 'single_choice' || busy) return
    const key = (event: KeyboardEvent) => {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      )
        return
      const index = Number(event.key) - 1
      if (index >= 0 && index < item.options.length) {
        event.preventDefault()
        const optId = item.options[index].id
        setSelected(optId)
        void answer(optId)
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [phase, item, busy, answer])

  // Enter key to continue in feedback phase
  useEffect(() => {
    if (phase !== 'feedback') return
    const key = (event: KeyboardEvent) => {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      )
        return
      if (event.key === 'Enter') {
        event.preventDefault()
        next()
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [phase, next])

  const handleExitClick = () => {
    preparation.current?.abort()
    if (!session || session.phase === 'complete' || Object.keys(session.attempts).length === 0) {
      if (session && session.phase !== 'complete' && accountId && nodeId) {
        discardSession(accountId, nodeId)
      }
      router.push(backHref)
      return
    }
    setExitDialogOpen(true)
  }

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !exitDialogOpen) {
        if (session && session.phase !== 'complete' && Object.keys(session.attempts).length > 0) {
          e.preventDefault()
          setExitDialogOpen(true)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [exitDialogOpen, session])

  function restart() {
    discardSession(accountId, nodeId)
    lastSaved.current = null
    setSession(null)
    setBlocked(false)
    setError('')
  }
  return { restart, router, account, params, profile, accountId, nodeId, selection, backHref, session, starting, busy, error, submitError, blocked, selected, setSelected, names, exitDialogOpen, setExitDialogOpen, preparation, item, typed, question, attempt, total, finished, selectedOption, commit, start, answer, next, submit, handleExitClick }
}
