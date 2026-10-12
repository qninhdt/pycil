'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, ChevronDown, RotateCcw, X } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { Background } from '@/components/artwork/artwork'
import { MarkedText } from '@/components/content/marked-text'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { flashcardArtwork } from '@/lib/flashcard-artwork'
import { DotGridWave } from './dot-grid-wave'
import { useServices } from '@/lib/services/provider'
import {
  advanceSession,
  beginAttempt,
  finishSession,
  allQuestions,
  completedCount,
  createStudySession,
  currentQuestion,
  discardSession,
  loadSession,
  pruneStaleSessions,
  recordAttempt,
  saveSession,
  sessionKey,
  startNextRound,
  type StudySession,
} from '@/lib/study-session'
import { HomeApiError, type Diagnostic, type PreparedQuestion, type QuestionOption, type SessionSelection } from '@/lib/home-api'
import { libraryHref, publishedHref } from '@/lib/library-model'
import { useTranslations } from 'next-intl'

export function Prompt({
  item,
  typed = '',
  selectedOption,
}: {
  item: PreparedQuestion
  typed?: string
  selectedOption?: QuestionOption
}) {
  const t = useTranslations('learning')
  const { question } = item
  const missingTurnRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (missingTurnRef.current) {
      missingTurnRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [item, selectedOption?.id])

  // 1. DIALOGUE_COMPLETION (Messenger / WhatsApp style chat)
  if (question.question_type === 'DIALOGUE_COMPLETION' && Array.isArray(question.content)) {
    const turns = question.content
    const hiddenIndex = turns.findIndex(turn => turn.text === null)
    const userSpeaker = hiddenIndex >= 0 ? turns[hiddenIndex].speaker : 'You'
    const partnerTurn = turns.find(turn => turn.speaker !== userSpeaker)
    const partnerSpeaker = partnerTurn?.speaker ?? 'Contact'
    const partnerInitial = (partnerSpeaker[0] ?? '?').toUpperCase()

    return (
      <div
        className="mb-6 border-2 border-foreground bg-background shadow-xs w-full overflow-hidden"
        aria-label={t('dialogueAria')}
      >
        {/* Messenger / WhatsApp chat window header */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-foreground bg-muted/30">
          <div className="flex items-center gap-3">
            <div className="relative">
              <span className="size-8 rounded-full bg-art-yellow border border-foreground text-foreground flex items-center justify-center text-xs font-black shrink-0">
                {partnerInitial}
              </span>
              <span className="absolute bottom-0 right-0 size-2.5 rounded-full bg-emerald-500 border border-background" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-extrabold text-foreground leading-none">{partnerSpeaker}</span>
              <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-mono font-medium leading-tight mt-1">{t('online')}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-[11px] font-mono font-bold bg-art-blue/10 text-art-blue border border-art-blue/30 rounded-xs">
              {t('replyingAs', { speaker: userSpeaker })}
            </span>
          </div>
        </div>

        {/* Chat message thread with constrained scroll container and themed scrollbar */}
        <div
          tabIndex={0}
          aria-label={t('conversationMessagesAria')}
          className="p-5 sm:p-6 flex flex-col gap-4 bg-[color-mix(in_srgb,var(--muted)_25%,var(--background))] max-h-[320px] sm:max-h-[380px] overflow-y-auto overscroll-contain focus-dialogue-scrollbar focus:outline-none"
        >
          {turns.map((turn, index) => {
            const isUserTurn = turn.text === null
            const isUserSpeaker = turn.speaker === userSpeaker
            const timeMinute = 20 + index
            const timeStr = `10:${timeMinute < 10 ? '0' + timeMinute : timeMinute} AM`

            if (isUserTurn) {
              return (
                <div
                  key={index}
                  ref={missingTurnRef}
                  className="flex flex-col items-end self-end max-w-[85%] sm:max-w-[75%]"
                  data-empty={!selectedOption}
                >
                  <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 mr-1">
                    {t('youSpeaker', { name: userSpeaker })}
                  </span>
                  {selectedOption ? (
                    <div className="px-4.5 py-3 rounded-2xl rounded-tr-xs bg-art-blue text-white shadow-xs font-medium text-[15px] sm:text-base leading-relaxed [&_mark]:bg-white/25 [&_mark]:text-white [&_mark]:border-b-2 [&_mark]:border-white [&_mark]:shadow-xs">
                      <MarkedText text={selectedOption.content} />
                      <div className="text-[10px] text-white/80 font-mono text-right mt-1.5 flex items-center justify-end gap-1">
                        <span>{timeStr}</span>
                        <span className="font-bold">✓✓</span>
                      </div>
                    </div>
                  ) : (
                    <div className="px-4.5 py-3 rounded-2xl rounded-tr-xs border-2 border-dashed border-art-blue bg-art-blue/10 text-art-blue font-medium text-sm sm:text-base flex items-center gap-2.5 transition-all">
                      <span className="flex gap-1 items-center" aria-hidden="true">
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce [animation-delay:-0.3s]" />
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce [animation-delay:-0.15s]" />
                        <span className="size-1.5 rounded-full bg-art-blue animate-bounce" />
                      </span>
                      <span className="italic">{t('chooseReplyBelow')}</span>
                    </div>
                  )}
                </div>
              )
            }

            if (isUserSpeaker) {
              return (
                <div
                  key={index}
                  className="flex flex-col items-end self-end max-w-[85%] sm:max-w-[75%]"
                >
                  <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 mr-1">
                    {userSpeaker}
                  </span>
                  <div className="px-4.5 py-3 rounded-2xl rounded-tr-xs bg-art-blue text-white shadow-xs font-medium text-[15px] sm:text-base leading-relaxed [&_mark]:bg-white/25 [&_mark]:text-white [&_mark]:border-b-2 [&_mark]:border-white [&_mark]:shadow-xs">
                    <p className="m-0 font-medium">
                      <MarkedText text={turn.text ?? ''} />
                    </p>
                    <div className="text-[10px] text-white/80 font-mono text-right mt-1.5 flex items-center justify-end gap-1">
                      <span>{timeStr}</span>
                      <span className="font-bold">✓✓</span>
                    </div>
                  </div>
                </div>
              )
            }

            return (
              <div
                key={index}
                className="flex flex-col items-start self-start max-w-[85%] sm:max-w-[75%]"
              >
                <span className="text-[11px] font-extrabold text-muted-foreground/80 mb-1 ml-1">
                  {turn.speaker}
                </span>
                <div className="px-4.5 py-3 rounded-2xl rounded-tl-xs bg-background border border-foreground/20 text-foreground text-[15px] sm:text-base leading-relaxed shadow-xs">
                  <p className="m-0 font-medium">
                    <MarkedText text={turn.text ?? ''} />
                  </p>
                  <span className="text-[10px] text-muted-foreground/70 font-mono block text-right mt-1.5">
                    {timeStr}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  const content = typeof question.content === 'string' ? question.content : ''

  // 2. CLOZE_TO_WORD (The Dynamic Editorial Stamp)
  if (question.question_type === 'CLOZE_TO_WORD') {
    const [before, after] = content.split('_')
    const activeWord = item.format === 'SINGLE_WORD' ? typed : selectedOption ? selectedOption.content : ''

    return (
      <div className="mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background w-full">
        <p className="text-xl sm:text-2xl font-semibold leading-relaxed text-foreground text-pretty m-0">
          <MarkedText text={before} />
          <span
            className="inline-flex items-baseline px-3 py-0.5 mx-1.5 border-b-2 border-art-blue bg-[color-mix(in_srgb,var(--art-blue)_14%,var(--background))] font-mono text-[0.88em] font-bold text-art-blue transition-all"
            aria-label={t('missingWordAria')}
          >
            {activeWord ? activeWord : '_______'}
          </span>
          <MarkedText text={after ?? ''} />
        </p>
      </div>
    )
  }

  // 3. WORD_TO_USAGE (The Author’s Atelier)
  if (question.question_type === 'WORD_TO_USAGE') {
    const [word, meaning] = content.split(' — ')
    return (
      <div className="mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border-l-4 border-art-red border-y border-r border-foreground bg-background w-full">
        <strong className="block text-2xl sm:text-3xl font-black tracking-tight text-foreground leading-tight wrap-anywhere mb-1.5">
          <MarkedText text={word} />
        </strong>
        <p className="text-sm sm:text-base text-muted-foreground leading-relaxed font-normal m-0">{meaning}</p>
      </div>
    )
  }

  // 4. WORD_TO_DEFINITION (The Lexicon Monolith)
  if (question.question_type === 'WORD_TO_DEFINITION') {
    return (
      <div className="mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background flex flex-col justify-center w-full">
        <strong className="block text-3xl sm:text-4xl font-black tracking-tight text-foreground leading-tight wrap-anywhere">
          <MarkedText text={content} />
        </strong>
      </div>
    )
  }

  // 5. MEANING_IN_CONTEXT (The Excerpt Monocle)
  if (question.question_type === 'MEANING_IN_CONTEXT') {
    return (
      <blockquote className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background">
        <p className="text-base sm:text-lg font-medium leading-relaxed text-foreground m-0">
          <MarkedText text={content} />
        </p>
      </blockquote>
    )
  }

  // 6. DEFINITION_TO_WORD (The Reverse Codex)
  if (question.question_type === 'DEFINITION_TO_WORD') {
    return (
      <div className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border-l-4 border-foreground border-y border-r border-foreground bg-background">
        <blockquote className="text-base sm:text-lg font-medium leading-relaxed text-foreground m-0">
          &ldquo;<MarkedText text={content} />&rdquo;
        </blockquote>
      </div>
    )
  }

  // 7. CONTEXT_TO_WORD (The Case Dossier) - Strip "In this situation:" prefix!
  if (question.question_type === 'CONTEXT_TO_WORD') {
    const cleanedContext = content.replace(/^In this situation:\s*/i, '')
    return (
      <div className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background">
        <p className="text-base sm:text-lg leading-relaxed text-foreground m-0">
          <MarkedText text={cleanedContext} />
        </p>
      </div>
    )
  }

  // 8. SENTENCE_REWRITE
  return (
    <div className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background">
      <blockquote className="relative m-0 pl-4 before:absolute before:top-1 before:bottom-1 before:left-0 before:w-[2px] before:bg-art-blue">
        <p className="text-xl sm:text-2xl font-medium leading-relaxed text-foreground text-pretty m-0">
          &ldquo;<MarkedText text={content} />&rdquo;
        </p>
      </blockquote>
    </div>
  )
}

export function GradeDetails({ grade }: { grade: Diagnostic | null }) {
  const [open, setOpen] = useState(false)
  const t = useTranslations('learning')
  const tCommon = useTranslations('common')
  if (!grade) return null

  const d = grade as Record<string, unknown>
  const pills: { key: string; label: string; value: string; status: 'pass' | 'fail' | 'warn' }[] = []

  if (typeof d.correct === 'boolean') {
    pills.push({
      key: 'correct',
      label: t('meaningMatch'),
      value: d.correct ? t('correct') : t('needsWork'),
      status: d.correct ? 'pass' : 'fail',
    })
  }

  if (typeof d.task_fit === 'boolean') {
    pills.push({
      key: 'task_fit',
      label: t('taskFit'),
      value: d.task_fit ? t('correct') : t('needsWork'),
      status: d.task_fit ? 'pass' : 'fail',
    })
  }

  if (typeof d.meaning === 'string' && d.meaning) {
    const isExact = d.meaning === 'CORRECT' || d.meaning === 'EXACT'
    const isRelated = d.meaning === 'APPROXIMATE' || d.meaning === 'RELATED'
    pills.push({
      key: 'meaning',
      label: t('meaningMatch'),
      value: isExact ? t('exact') : isRelated ? t('exact') : t('needsWork'),
      status: isExact ? 'pass' : isRelated ? 'warn' : 'fail',
    })
  }

  if (typeof d.accuracy === 'string' && d.accuracy) {
    const isAccurate = d.accuracy === 'ACCURATE'
    pills.push({
      key: 'accuracy',
      label: t('meaningMatch'),
      value: isAccurate ? t('correct') : d.accuracy.toLowerCase(),
      status: isAccurate ? 'pass' : 'warn',
    })
  }

  if (typeof d.spelling_error === 'boolean') {
    pills.push({
      key: 'spelling',
      label: t('formMatch'),
      value: d.spelling_error ? t('spellingIssue') : t('noSpellingError'),
      status: d.spelling_error ? 'warn' : 'pass',
    })
  } else if (typeof d.form === 'string' && d.form) {
    const isCorrect = d.form === 'CORRECT'
    pills.push({
      key: 'form',
      label: t('formMatch'),
      value: isCorrect ? t('correct') : String(d.form).toLowerCase().replaceAll('_', ' '),
      status: isCorrect ? 'pass' : 'warn',
    })
  }

  if (typeof d.construction === 'boolean' && d.construction !== null) {
    pills.push({
      key: 'construction',
      label: t('grammarConstruction'),
      value: d.construction ? t('correct') : t('needsWork'),
      status: d.construction ? 'pass' : 'fail',
    })
  }

  if (typeof d.collocation === 'boolean' && d.collocation !== null) {
    pills.push({
      key: 'collocation',
      label: t('collocationUsage'),
      value: d.collocation ? t('naturalCollocation') : t('needsWork'),
      status: d.collocation ? 'pass' : 'warn',
    })
  }

  if (typeof d.appropriacy === 'boolean' && d.appropriacy !== null) {
    pills.push({
      key: 'appropriacy',
      label: t('appropriacyUsage'),
      value: d.appropriacy ? t('correct') : t('needsWork'),
      status: d.appropriacy ? 'pass' : 'warn',
    })
  }

  if (typeof d.meaning_preservation === 'string' && d.meaning_preservation) {
    const isPreserved = d.meaning_preservation === 'PRESERVED' || d.meaning_preservation === 'EXACT'
    pills.push({
      key: 'preservation',
      label: t('nuancePreserved'),
      value: isPreserved ? t('exact') : String(d.meaning_preservation).toLowerCase().replaceAll('_', ' '),
      status: isPreserved ? 'pass' : 'warn',
    })
  }

  const allEntries = Object.entries(grade).filter(([key]) => key !== 'sense_id')

  return (
    <div className="mt-3 pt-3 border-t border-border/80">
      <div className="flex items-center flex-wrap gap-2 text-xs">
        {pills.map(pill => (
          <span
            key={pill.key}
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 border text-[11px] font-semibold ${
              pill.status === 'pass'
                ? 'border-art-blue/40 bg-art-blue/10 text-art-blue'
                : pill.status === 'fail'
                  ? 'border-art-red/40 bg-art-red/10 text-art-red'
                  : 'border-art-yellow/40 bg-art-yellow/15 text-art-yellow'
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${
                pill.status === 'pass'
                  ? 'bg-art-blue'
                  : pill.status === 'fail'
                    ? 'bg-art-red'
                    : 'bg-art-yellow'
              }`}
              aria-hidden="true"
            />
            <span className="text-muted-foreground font-normal">{pill.label}:</span>
            <span>{pill.value}</span>
          </span>
        ))}
        {allEntries.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen(prev => !prev)}
            className="inline-flex items-center gap-1 text-[11px] font-bold text-muted-foreground hover:text-foreground underline decoration-dotted underline-offset-2 ml-auto cursor-pointer"
            aria-expanded={open}
          >
            {t('diagnosticDetails')}
            <ChevronDown className={`size-3 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
        )}
      </div>

      {open && (
        <div className="mt-2.5 p-3 bg-muted/40 border border-border text-xs">
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {allEntries.map(([key, value]) => (
              <div key={key} className="flex flex-col gap-0.5">
                <dt className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">
                  {key.replaceAll('_', ' ')}
                </dt>
                <dd className="font-semibold text-foreground capitalize">
                  {value === null
                    ? tCommon('notAssessed')
                    : typeof value === 'boolean'
                      ? value
                        ? tCommon('yes')
                        : tCommon('no')
                      : String(value).replaceAll('_', ' ').toLowerCase()}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  )
}

export function QuizFocus({ initialSession }: { initialSession?: StudySession } = {}) {
  const router = useRouter()
  const account = useAccount(),
    { services } = useServices(),
    params = useSearchParams()
  const queryClient = useQueryClient()
  const t = useTranslations('learning')
  const tCommon = useTranslations('common')
  const tNav = useTranslations('nav')
  const tLib = useTranslations('library')
  const tHome = useTranslations('home')
  const profile = account.profile,
    accountId = profile?.id ?? ''
  const nodeId = params?.get('node') || profile?.library_node_id || ''
  const selection = (
    params?.get('selection') === 'NEW' || params?.get('selection') === 'DUE' ? params?.get('selection') : 'AUTO'
  ) as SessionSelection
  const backHref = params?.get('owner') && nodeId ? publishedHref(params.get('owner')!, nodeId) : libraryHref(nodeId)
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
  const [resumedToast, setResumedToast] = useState(false)
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
    const existing = loadSession(accountId, nodeId)
    if (existing && existing.phase !== 'complete') {
      lastSaved.current = localStorage.getItem(sessionKey(accountId, nodeId))
      setSession(existing)
      if (completedCount(existing) > 0) {
        setResumedToast(true)
      }
    } else {
      if (existing?.phase === 'complete') {
        discardSession(accountId, nodeId)
      }
      lastSaved.current = null
      setSession(null)
    }
    setBlocked(false)
    setHydrated(true)
  }, [accountId, nodeId, initialSession])

  useEffect(() => {
    if (resumedToast) {
      const timer = setTimeout(() => setResumedToast(false), 3000)
      return () => clearTimeout(timer)
    }
  }, [resumedToast])

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

  async function start() {
    if (!profile || starting || !nodeId) return
    setStarting(true)
    setError('')
    setBlocked(false)
    try {
      const prepared = await services.learning.prepare({ node_id: nodeId, selection }, new AbortController().signal)
      if (!prepared.bundles.length) {
        setError(t('noEligibleQuestions'))
        return
      }
      commit(createStudySession(profile.id, prepared))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('couldNotPrepareSession'))
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (!hydrated || initialSession || session || starting || !profile || !nodeId || error) return
    void start()
  }, [hydrated, initialSession, session, starting, profile, nodeId, error])

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
      if (item.format === 'SINGLE_CHOICE') {
        if (pending.answer !== null && !item.options.some(option => option.id === pending.answer)) throw new Error(t('chooseAvailableAnswer'))
        diagnostics = { correct: pending.answer === item.question.correct.id }
      } else {
        const grade = await services.learning.grade({ question_artifact_id: item.question.question_artifact_id,
          question_type: item.question.question_type, format: item.format, answer: pending.answer }, new AbortController().signal)
        if (grade.question_artifact_id !== item.question.question_artifact_id || grade.question_type !== item.question.question_type || grade.format !== item.format) throw new HomeApiError(502, 'invalid_response')
        diagnostics = grade.diagnostics
      }
      commit(recordAttempt(locked, diagnostics))
    } catch (cause) {
      if (
        cause instanceof HomeApiError &&
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
        })) throw new HomeApiError(502, 'invalid_response')
        if (!commit({ ...current, receipt, phase: 'complete' }))
          setSubmitError(t('resultsAcceptedStorageError'))
        await queryClient.invalidateQueries({ queryKey: [services.mode] })
      } catch (cause) {
        setSubmitError(cause instanceof Error ? cause.message : t('resultsNotConfirmed'))
      } finally {
        submitting.current = false
      }
    },
    [commit, services.learning, services.mode, queryClient, t]
  )

  useEffect(() => {
    if (session?.phase === 'submitting' && !session.receipt) void submit(session)
  }, [session, submit])

  // Instant keyboard submission on 1-4 for SINGLE_CHOICE
  useEffect(() => {
    if (phase !== 'question' || !item || item.format !== 'SINGLE_CHOICE' || busy) return
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

  if (!initialSession && (account.status !== 'ready' || !profile)) {
    return (
      <main className="h-svh max-h-svh overflow-hidden flex flex-col items-center justify-center p-8 bg-background text-foreground">
        <div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground">
          <h1>{t('learnTitle')}</h1>
          <p>{account.status === 'loading' ? tNav('loadingAccount') : t('signInToStudy')}</p>
          <Button asChild>
            <Link href="/login">{tCommon('signIn')}</Link>
          </Button>
        </div>
      </main>
    )
  }

  if (!initialSession && session && session.accountId !== accountId) {
    return (
      <main className="h-svh max-h-svh overflow-hidden flex flex-col items-center justify-center p-8 bg-background text-foreground">
        <div className="max-w-[680px] flex flex-col items-start gap-5 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground">
          <h1>{t('learnTitle')}</h1>
          <p>{t('restoringSession')}</p>
        </div>
      </main>
    )
  }

  if (!session) {
    if (error) {
      return (
        <main className="h-svh max-h-svh overflow-hidden flex flex-col items-center justify-center p-8 bg-background text-foreground">
          <div className="max-w-[560px] flex flex-col items-start gap-5">
            <Link className="inline-flex items-center gap-2 text-[13px] underline underline-offset-4" href={backHref}>
              <ArrowLeft aria-hidden="true" /> {tLib('backToLibrary')}
            </Link>
            <h1 className="text-[clamp(28px,3.5vw,44px)] leading-[1.1] font-extrabold tracking-tight">{t('learnTitle')}</h1>
            <p className="text-art-red text-sm font-semibold" role="alert">{error}</p>
            <div className="flex flex-wrap gap-2.5 pt-2">
              <Button
                onClick={() => {
                  void start()
                }}
                disabled={starting}
              >
                {starting ? t('preparingQuestions') : (tCommon('retry') ?? 'Retry')}
              </Button>
              <Button variant="outline" asChild>
                <Link href={backHref}>{tLib('backToLibrary')}</Link>
              </Button>
            </div>
          </div>
        </main>
      )
    }

    return (
      <main className="h-svh max-h-svh overflow-hidden flex flex-col bg-background text-foreground">
        <header className="flex-none h-[78px] grid grid-cols-[78px_minmax(120px,1fr)_minmax(190px,420px)_minmax(120px,1fr)] items-center border-b border-foreground max-[760px]:h-16 max-[760px]:grid-cols-[56px_minmax(0,1fr)_auto]">
          <button
            type="button"
            onClick={handleExitClick}
            className="grid place-items-center h-full border-r border-foreground hover:bg-accent text-foreground transition-colors cursor-pointer"
            aria-label={t('exitLearningMode')}
            title={t('exitLearningMode')}
          >
            <X aria-hidden="true" className="size-6" />
          </button>
          <div className="flex gap-3 items-baseline min-w-0 px-6 whitespace-nowrap overflow-hidden text-ellipsis [&_strong]:font-extrabold [&_span]:text-muted-foreground max-[760px]:px-3 max-[760px]:gap-2 max-[760px]:text-[13px]">
            <strong>{t('pycilLearn')}</strong>
            <span>{selection === 'DUE' ? tLib('review') : selection === 'NEW' ? tLib('learnNew') : tHome('practice')}</span>
          </div>
          <div className="flex items-center gap-4 min-w-0 max-[760px]:pr-4 max-[760px]:pl-2">
            <div className="w-20 sm:w-full h-2 bg-muted overflow-hidden">
              <div className="h-full bg-art-blue shimmer shimmer-bg w-full" />
            </div>
          </div>
          <div className="flex items-center justify-end px-6 max-[760px]:hidden">
            <span className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              {t('preparingQuestions')}
            </span>
          </div>
        </header>

        <div className="flex-1 min-h-0 flex flex-col items-center justify-center p-3 sm:p-5 md:p-6 overflow-y-auto overflow-x-hidden">
          <article className="focus-card isolate relative w-[min(100%,1040px)] flex-1 max-[760px]:flex-initial max-[760px]:h-auto min-h-0 max-h-[calc(100svh-148px)] max-[760px]:max-h-[calc(100svh-88px)] my-auto flex flex-col items-center justify-center overflow-hidden border border-foreground bg-background p-6">
            <DotGridWave />
          </article>
        </div>

        <AlertDialog open={exitDialogOpen} onOpenChange={setExitDialogOpen}>
          <AlertDialogContent size="sm" className="max-w-[420px] border border-foreground p-6 rounded-none">
            <AlertDialogHeader className="space-y-2">
              <AlertDialogTitle className="text-xl font-extrabold tracking-tight">
                {t('cancelPreparingTitle')}
              </AlertDialogTitle>
              <AlertDialogDescription className="text-sm text-muted-foreground leading-relaxed">
                {t('cancelPreparingDesc')}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="flex flex-col gap-2.5 pt-4">
              <Button
                type="button"
                className="w-full justify-center font-bold rounded-none"
                onClick={() => setExitDialogOpen(false)}
              >
                {t('keepWaiting')}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="justify-center rounded-none font-medium"
                onClick={() => {
                  setExitDialogOpen(false)
                  router.push(backHref)
                }}
              >
                {t('cancelAndExit')}
              </Button>
            </div>
          </AlertDialogContent>
        </AlertDialog>
      </main>
    )
  }

  const clearedThisRound = session.questions.filter(id => session.attempts[id]?.at(-1)?.complete).length
  const reviewName = (senseId: number) => {
    const bundle = session.prepared.bundles.find(value => value.sense.id === senseId)
    return bundle
      ? names[bundle.sense.word_id] ?? bundle.sense.definition?.content ?? t('meaningNumber', { id: senseId })
      : t('meaningNumber', { id: senseId })
  }

  const questionLabels: Record<string, string> = {
    DEFINITION_TO_WORD: t('findTheWord'),
    CONTEXT_TO_WORD: t('readTheContext'),
    CLOZE_TO_WORD: t('completeTheSentence'),
    WORD_TO_DEFINITION: t('explainTheMeaning'),
    WORD_TO_USAGE: t('useThisMeaning'),
    DIALOGUE_COMPLETION: t('completeTheDialogue'),
    MEANING_IN_CONTEXT: t('meaningInContext'),
    SENTENCE_REWRITE: t('rewriteTheSentence'),
  }

  // Helper metrics for WORD_TO_USAGE & SENTENCE_REWRITE
  const usageWordCount = typed.trim() ? typed.trim().split(/\s+/).length : 0
  const isUsageQuestion = question?.question_type === 'WORD_TO_USAGE'
  const isRewriteQuestion = question?.question_type === 'SENTENCE_REWRITE'
  const targetUsageLemma = isUsageQuestion && typeof question.content === 'string' ? question.content.split(' — ')[0] : ''
  const bundle = session?.prepared?.bundles?.find(b => b.sense.id === question?.sense_id)
  const targetRewriteLemma = isRewriteQuestion
    ? (bundle?.sense?.forms?.[0]?.surface) ||
      (bundle ? names[bundle.sense.word_id] : '') ||
      (question && typeof question.correct?.content === 'string'
        ? question.correct.content.match(/\[([^|\]]+)(?:\|[^\]]+)?\]/)?.[1]
        : '') ||
      ''
    : ''
  const rewriteForms = isRewriteQuestion
    ? [
        targetRewriteLemma,
        ...(bundle?.sense?.forms?.map(f => f.surface) ?? []),
        ...(question && typeof question.correct?.content === 'string'
          ? [question.correct.content.match(/\[([^|\]]+)(?:\|[^\]]+)?\]/)?.[1] ?? '']
          : []),
      ].filter(Boolean)
    : []
  const hasIncludedUsageWord = Boolean(targetUsageLemma && typed.toLowerCase().includes(targetUsageLemma.toLowerCase()))
  const hasIncludedRewriteWord = Boolean(rewriteForms.some(form => form && typed.toLowerCase().includes(form.toLowerCase())))

  // Determine option layout strategy based on question archetype
  const isStackedLayout =
    question?.question_type === 'DIALOGUE_COMPLETION' ||
    question?.question_type === 'MEANING_IN_CONTEXT' ||
    question?.question_type === 'SENTENCE_REWRITE'

  return (
    <main className="h-svh max-h-svh overflow-hidden flex flex-col bg-background text-foreground">
      <header className="flex-none h-[78px] grid grid-cols-[78px_minmax(120px,1fr)_minmax(190px,420px)_minmax(120px,1fr)] items-center border-b border-foreground max-[760px]:h-16 max-[760px]:grid-cols-[56px_minmax(0,1fr)_auto]">
        <button
          type="button"
          onClick={handleExitClick}
          className="grid place-items-center h-full border-r border-foreground hover:bg-accent text-foreground transition-colors cursor-pointer"
          aria-label={t('exitLearningMode')}
          title={t('exitLearningMode')}
        >
          <X aria-hidden="true" className="size-6" />
        </button>
        <div className="flex gap-3 items-baseline min-w-0 px-6 whitespace-nowrap overflow-hidden text-ellipsis [&_strong]:font-extrabold [&_span]:text-muted-foreground max-[760px]:px-3 max-[760px]:gap-2 max-[760px]:text-[13px] max-[760px]:[&_strong]:overflow-hidden max-[760px]:[&_strong]:text-ellipsis">
          <strong>{t('pycilLearn')}</strong>
          <span>{selection === 'DUE' ? tLib('review') : selection === 'NEW' ? tLib('learnNew') : tHome('practice')}</span>
        </div>
        <div className="flex items-center gap-2.5 sm:gap-4 min-w-0 [&_small]:flex-none [&_small]:text-xs [&_small]:text-muted-foreground [&_small]:tabular-nums max-[760px]:pr-4 max-[760px]:pl-2">
          <div className="w-16 sm:w-full h-2 bg-muted overflow-hidden [&_span]:block [&_span]:h-full [&_span]:bg-foreground [&_span]:transition-[width] [&_span]:duration-200 [&_span]:ease-out max-[760px]:min-w-[18px] motion-reduce:[&_span]:transition-none">
            <span style={{ width: `${total ? (finished / total) * 100 : 0}%` }} />
          </div>
          <small className="max-[760px]:hidden">
            {t('finishedCount', { finished, total })}
            {session.retry.length ? ` · ${t('toRetryCount', { count: session.retry.length })}` : ''}
          </small>
          <small className="hidden max-[760px]:block max-[760px]:text-[11px] font-mono">
            {finished}/{total}
          </small>
        </div>
        <div className="flex items-center justify-end px-6 max-[760px]:hidden">
          <span className="text-right text-[13px] tabular-nums text-muted-foreground">
            {session.phase === 'question' || session.phase === 'feedback'
              ? t('roundPosition', { round: session.round, pos: session.position + 1, total: session.questions.length })
              : t('round', { round: session.round })}
          </span>
        </div>
      </header>

      {session.phase === 'question' || session.phase === 'feedback' ? (
        item ? (
          <div className="flex-1 min-h-0 flex flex-col items-center justify-center p-3 sm:p-5 md:p-6 overflow-y-auto overflow-x-hidden">
            <article className="focus-card isolate relative w-[min(100%,1040px)] flex-1 max-[760px]:flex-initial max-[760px]:h-auto min-h-0 max-h-[calc(100svh-148px)] max-[760px]:max-h-[calc(100svh-88px)] my-auto flex flex-col overflow-hidden border border-foreground bg-background">
              <div
                className="absolute inset-0 -z-[1] pointer-events-none [&_>_svg]:w-full [&_>_svg]:h-full after:content-[''] after:absolute after:inset-0 after:bg-[color-mix(in_srgb,var(--background)_90%,transparent)]"
                aria-hidden="true"
              >
                <Background name={flashcardArtwork(`${session.seed}:${session.questions[session.position]}`)} />
              </div>

              <div className="focus-card-body w-[min(100%,860px)] m-auto flex-1 max-[760px]:flex-initial max-[760px]:h-auto min-h-0 flex flex-col justify-center overflow-y-auto px-4 py-5 sm:px-10 sm:py-8 max-[760px]:mx-auto">
                <h1 className="text-xl sm:text-2xl md:text-[28px] font-black text-foreground mb-4 sm:mb-6 tracking-tight leading-tight">
                  {question!.question_type === 'DEFINITION_TO_WORD'
                    ? t('promptWhichWordMatches')
                    : question!.question_type === 'CONTEXT_TO_WORD'
                      ? t('promptWhichWordFits')
                      : question!.question_type === 'CLOZE_TO_WORD'
                        ? t('completeTheSentence')
                        : question!.question_type === 'DIALOGUE_COMPLETION'
                          ? t('promptChooseBestReply')
                          : question!.question_type === 'MEANING_IN_CONTEXT'
                            ? t('promptWhatDoesHighlightedMean')
                            : question!.question_type === 'WORD_TO_DEFINITION'
                              ? t('explainTheMeaning')
                              : question!.question_type === 'SENTENCE_REWRITE'
                                ? targetRewriteLemma
                                  ? t('promptRewriteUsing', { lemma: targetRewriteLemma })
                                  : t('rewriteTheSentence')
                                : questionLabels[question!.question_type]}
                </h1>

                <Prompt item={item} typed={typed} selectedOption={selectedOption} />

                {session.phase === 'question' && (
                  <form
                    className="focus-answer w-full"
                    onSubmit={event => {
                      event.preventDefault()
                      void answer(item.format === 'SINGLE_CHOICE' ? selected : typed)
                    }}
                  >
                    {item.format === 'SINGLE_CHOICE' ? (
                      <fieldset className="w-full">
                        <legend className="sr-only">{t('chooseOneAnswer')}</legend>
                        <div
                          className={`focus-options w-full grid gap-2.5 sm:gap-3 ${
                            isStackedLayout
                              ? 'grid-cols-1'
                              : 'grid-cols-2 max-[760px]:grid-cols-1'
                          }`}
                        >
                          {item.options.map((option, index) => (
                            <button
                              key={option.id}
                              type="button"
                              aria-pressed={selected === option.id}
                              disabled={busy}
                              onClick={() => {
                                setSelected(option.id)
                                void answer(option.id)
                              }}
                              className="min-h-[52px] sm:min-h-[60px] flex items-center gap-3.5 px-3.5 py-2.5 sm:px-4 sm:py-3 border border-foreground bg-background text-left leading-snug transition-colors duration-150 hover:bg-accent aria-pressed:bg-[color-mix(in_srgb,var(--art-blue)_15%,var(--background))] aria-pressed:border-art-blue aria-pressed:ring-1 aria-pressed:ring-art-blue motion-reduce:transition-none cursor-pointer"
                            >
                              <span
                                className={`grid place-items-center size-7 flex-none border text-xs font-mono font-bold tabular-nums transition-colors ${
                                  selected === option.id
                                    ? 'bg-art-blue text-white border-art-blue'
                                    : 'border-foreground/30 bg-muted/40 text-foreground'
                                }`}
                              >
                                {index + 1}
                              </span>
                              <span className="font-semibold text-[15px] text-foreground leading-normal">
                                <MarkedText text={option.content} />
                              </span>
                            </button>
                          ))}
                        </div>
                      </fieldset>
                    ) : item.format === 'SINGLE_WORD' ? (
                      <div className="mt-2 w-full">
                        <label
                          htmlFor="single-word-input"
                          className="sr-only"
                        >
                          {t('yourWord')}
                        </label>
                        <input
                          id="single-word-input"
                          aria-label={t('yourWord')}
                          autoComplete="off"
                          autoFocus
                          value={typed}
                          disabled={busy || Boolean(session.pendingAttempt)}
                          onChange={event => {
                            if (session) commit({ ...session, draft: event.target.value })
                          }}
                          maxLength={8000}
                          placeholder={t('typeWordPlaceholder')}
                          className="w-full px-5 py-4 border-2 border-foreground bg-background text-foreground text-xl sm:text-2xl font-bold tracking-tight outline-none focus:border-art-blue focus:ring-2 focus:ring-art-blue/20 transition-all"
                        />
                      </div>
                    ) : (
                      <div className="mt-2 w-full">
                        <div className="flex items-center justify-between mb-2 px-0.5">
                          <label
                            htmlFor="short-answer-textarea"
                            className="sr-only"
                          >
                            {isRewriteQuestion ? t('yourRewrite') : t('yourAnswer')}
                          </label>
                          <div className="flex items-center gap-3 text-xs font-mono text-muted-foreground ml-auto">
                            <span>
                              {t('wordCountLabel', { count: usageWordCount })}
                            </span>
                            {hasIncludedUsageWord && (
                              <span className="text-success font-bold flex items-center gap-1">
                                ✓ {t('usedWord', { lemma: targetUsageLemma })}
                              </span>
                            )}
                            {hasIncludedRewriteWord && (
                              <span className="text-art-blue font-bold flex items-center gap-1.5">
                                <span className="size-2 bg-art-blue inline-block" />
                                {t('usedWord', { lemma: targetRewriteLemma })}
                              </span>
                            )}
                          </div>
                        </div>
                        <textarea
                          id="short-answer-textarea"
                          aria-label={isRewriteQuestion ? t('yourRewrite') : t('yourAnswer')}
                          autoFocus
                          value={typed}
                          disabled={busy || Boolean(session.pendingAttempt)}
                          onChange={event => {
                            if (session) commit({ ...session, draft: event.target.value })
                          }}
                          onKeyDown={event => {
                            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                              event.preventDefault()
                              void answer(typed)
                            }
                          }}
                          maxLength={8000}
                          rows={4}
                          placeholder={isRewriteQuestion ? t('rewritePlaceholder') : t('answerPlaceholder')}
                          className="w-full p-4 border-2 border-foreground bg-background text-foreground text-base sm:text-lg font-medium leading-relaxed outline-none focus:border-art-blue focus:ring-1 focus:ring-art-blue resize-y transition-colors"
                        />
                      </div>
                    )}

                    {error && (
                      <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">
                        {error}
                      </p>
                    )}

                    {/* Bottom action controls */}
                    <div className="flex items-center justify-between mt-4 sm:mt-6 pt-3 sm:pt-4 border-t border-border w-full">
                      <div className="text-xs text-muted-foreground font-mono max-[760px]:hidden">
                        {item.format === 'SINGLE_CHOICE' ? (
                          <span>{t('pressToChooseShortcut', { count: item.options.length })}</span>
                        ) : item.format === 'SINGLE_WORD' ? (
                          <span>{t('pressEnterToSubmit')}</span>
                        ) : (
                          <span>{t('pressCmdEnterToSubmit')}</span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 ml-auto">
                        {blocked ? (
                          <Button
                            type="button"
                            onClick={() => {
                              discardSession(accountId, nodeId)
                              lastSaved.current = null
                              setSession(null)
                              setBlocked(false)
                            }}
                          >
                            {t('startNewSession')}
                          </Button>
                        ) : item.format === 'SINGLE_CHOICE' ? (
                          <Button
                            type="button"
                            variant="ghost"
                            className="text-xs text-muted-foreground hover:text-foreground"
                            onClick={() => {
                              void answer('', true)
                            }}
                            disabled={busy}
                          >
                            {t('dontKnow')}
                          </Button>
                        ) : (
                          <>
                            <Button
                              type="button"
                              variant="outline"
                              onClick={() => {
                                void answer('', true)
                              }}
                              disabled={busy || Boolean(session.pendingAttempt)}
                            >
                              {t('dontKnow')}
                            </Button>
                            <Button
                              type="submit"
                              disabled={busy || (!session.pendingAttempt && !typed.trim())}
                              className="gap-2"
                            >
                              {busy ? t('checking') : session.pendingAttempt ? t('retryGrading') : t('checkAnswer')}
                              <kbd aria-hidden="true" className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono font-bold bg-primary-foreground/20 text-primary-foreground">
                                ↵
                              </kbd>
                            </Button>
                          </>
                        )}
                      </div>
                    </div>
                  </form>
                )}

                {session.phase === 'feedback' && attempt && (
                  <div
                    className="focus-feedback mt-6 border border-foreground bg-background w-full"
                    data-outcome={attempt.complete ? 'clear' : 'miss'}
                    role="status"
                  >
                    <div
                      className={`flex items-center justify-between gap-4 px-6 py-4 border-b ${
                        attempt.complete
                          ? 'border-art-blue/40 bg-art-blue/10 text-art-blue'
                          : 'border-art-red/40 bg-art-red/10 text-art-red'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span
                          className={`flex items-center justify-center size-7 border ${
                            attempt.complete
                              ? 'border-art-blue bg-art-blue text-background'
                              : 'border-art-red bg-art-red text-background'
                          }`}
                          aria-hidden="true"
                        >
                          {attempt.complete ? <Check className="size-4" /> : <RotateCcw className="size-4" />}
                        </span>
                        <strong className="text-lg font-black tracking-tight text-foreground">
                          {attempt.complete ? t('thatFits') : t('tryAgainNextRound')}
                        </strong>
                      </div>
                      <span className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground">
                        {attempt.complete ? 'Pass' : 'Next Pass'}
                      </span>
                    </div>

                    <div className="p-6">
                      {question!.question_type === 'SENTENCE_REWRITE' && attempt.answer && (
                        <div className="mb-4 p-3 bg-muted/40 border border-border text-sm">
                          <span className="block text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-1">
                            Your Rewrite
                          </span>
                          <p className="text-foreground italic m-0">
                            &ldquo;{attempt.answer}&rdquo;
                          </p>
                        </div>
                      )}

                      <div className="flex items-baseline gap-2 mb-2 text-base">
                        <span className="text-muted-foreground text-sm font-semibold">{t('answerLabel')}</span>
                        <strong className="text-foreground font-black text-lg">
                          <MarkedText text={question!.correct.content} />
                        </strong>
                      </div>

                      <GradeDetails grade={attempt.diagnostics} />

                      {error && (
                        <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">
                          {error}
                        </p>
                      )}

                      <div className="flex justify-end pt-5 mt-4 border-t border-border">
                        <Button onClick={next} size="lg" className="gap-2">
                          {t('continueButton')}
                          <kbd aria-hidden="true" className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono font-bold bg-primary-foreground/20 text-primary-foreground">
                            ↵
                          </kbd>
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </article>

            {/* Bottom Keyboard guidance bar */}
            <div className="flex-none w-[min(100%,1040px)] mt-2.5 mx-auto flex items-center justify-between text-xs text-muted-foreground max-[760px]:hidden">
              <div className="flex items-center gap-4">
                {session.phase === 'question' ? (
                  item.format === 'SINGLE_CHOICE' ? (
                    <span className="flex items-center gap-1.5 font-mono text-[11px]">
                      <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">1–{item.options.length}</kbd>
                      <span>{t('selectOptionAria')}</span>
                    </span>
                  ) : item.format === 'SINGLE_WORD' ? (
                    <span className="flex items-center gap-1.5 font-mono text-[11px]">
                      <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">Enter ↵</kbd>
                      <span>{t('submitWordAria')}</span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 font-mono text-[11px]">
                      <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">⌘ / Ctrl + Enter</kbd>
                      <span>{t('submitAnswerAria')}</span>
                    </span>
                  )
                ) : session.phase === 'feedback' ? (
                  <span className="flex items-center gap-1.5 font-mono text-[11px]">
                    <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">Enter ↵</kbd>
                    <span>{t('continueNextQuestionAria')}</span>
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        ) : null
      ) : null}

      {session.phase === 'recap' && (() => {
        const totalInRound = clearedThisRound + session.retry.length
        return (
          <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 md:p-8">
            <section className="w-[min(calc(100%-32px),880px)] my-2 mx-auto border-2 border-foreground bg-background shadow-xs overflow-hidden">
            {/* Architectural top status banner */}
            <div className="flex items-center justify-between px-6 sm:px-8 py-3.5 border-b border-border bg-muted/40">
              <div className="flex items-center gap-2" aria-hidden="true">
                <span className="size-2.5 rounded-full bg-art-red" />
                <span className="size-2.5 bg-art-blue" />
                <span className="size-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-b-[9px] border-b-art-yellow" />
                <span className="text-[11px] font-black uppercase tracking-widest text-muted-foreground ml-1">
                  {t('round', { round: session.round })}
                </span>
              </div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('roundRecap')}
              </span>
            </div>

            <div className="p-6 sm:p-10 md:p-12">
              <h1 className="text-3xl sm:text-4xl md:text-5xl font-black tracking-tight text-foreground leading-[1.1] mb-2.5">
                {session.retry.length ? t('readyForAnotherPass') : t('roundComplete')}
              </h1>
              <p className="text-sm sm:text-base text-muted-foreground max-w-[62ch] leading-relaxed mb-8">
                {session.retry.length > 0 ? t('tryAgainNextRound') : t('thatFits')}
              </p>

              {/* Pass / Retry Visual Breakdown Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 border-y-2 border-foreground py-6">
                <div className="p-5 sm:p-6 border border-border bg-card flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      {t('clearedThisRound')}
                    </span>
                    <span className="size-2.5 bg-art-blue" aria-hidden="true" />
                  </div>
                  <p className="flex items-baseline gap-2 m-0">
                    <strong className="text-4xl sm:text-5xl font-black tabular-nums text-foreground">
                      {clearedThisRound}
                    </strong>
                    <span className="text-xs font-semibold text-muted-foreground">
                      / {totalInRound}
                    </span>
                  </p>
                </div>

                <div className="p-5 sm:p-6 border border-border bg-card flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      {t('returningNextRound')}
                    </span>
                    <span className="size-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-b-[9px] border-b-art-yellow" aria-hidden="true" />
                  </div>
                  <p className="flex items-baseline gap-2 m-0">
                    <strong className="text-4xl sm:text-5xl font-black tabular-nums text-foreground">
                      {session.retry.length}
                    </strong>
                    <span className="text-xs font-semibold text-muted-foreground">
                      / {totalInRound}
                    </span>
                  </p>
                </div>
              </div>

              {/* Proportional rail */}
              <div
                className="h-2 w-full flex overflow-hidden border-x border-b border-foreground mb-8"
                aria-label={t('recapProgressAria', {
                  round: session.round,
                  cleared: clearedThisRound,
                  retry: session.retry.length,
                })}
              >
                <div
                  className="bg-art-blue transition-all duration-300"
                  style={{ width: `${totalInRound ? (clearedThisRound / totalInRound) * 100 : 0}%` }}
                />
                <div
                  className="bg-art-yellow transition-all duration-300"
                  style={{ width: `${totalInRound ? (session.retry.length / totalInRound) * 100 : 0}%` }}
                />
              </div>

              {/* Review card stack for returning items */}
              {session.retry.length > 0 && (
                <div className="mb-8">
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-xs font-black uppercase tracking-widest text-muted-foreground m-0">
                      {t('reviewBeforeContinuing')}
                    </h2>
                    <span className="text-xs font-bold tabular-nums text-muted-foreground">
                      {t('toRetryCount', { count: session.retry.length })}
                    </span>
                  </div>
                  <div className="divide-y divide-border border border-border bg-card">
                    {session.retry.map(id => {
                      const entry = allQuestions(session)[id]
                      return (
                        <div
                          key={id}
                          className="p-4 flex items-center justify-between gap-4 transition-colors hover:bg-muted/30"
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <span className="size-2 bg-art-yellow flex-none" aria-hidden="true" />
                            <span className="font-bold text-foreground text-sm sm:text-base truncate">
                              {entry ? reviewName(entry.question.sense_id) : t('questionNumber', { id })}
                            </span>
                          </div>
                          <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-bold border border-art-yellow/50 bg-art-yellow/10 text-art-yellow whitespace-nowrap">
                            {t('needsAnotherPass')}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {error && (
                <p className="mb-4 text-art-red text-xs font-semibold" role="alert">
                  {error}
                </p>
              )}

              <div className="pt-4 border-t border-border flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
                <span className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
                  <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">Enter ↵</kbd>
                  <span>{t('continueButton')}</span>
                </span>
                <Button
                  size="lg"
                  className="font-bold text-base px-8 py-3 rounded-none bg-foreground text-background hover:bg-foreground/90 transition-colors ml-auto cursor-pointer"
                  onClick={() => {
                    commit(startNextRound(session))
                  }}
                >
                  {t('continueToRound', { round: session.round + 1 })}
                </Button>
              </div>
            </div>
          </section>
        </div>
      )
    })()}

    {session.phase === 'submitting' && (
      <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 md:p-8 flex items-center justify-center">
        <section className="w-[min(calc(100%-32px),880px)] my-auto mx-auto border-2 border-foreground bg-background shadow-xs overflow-hidden p-8 sm:p-12 text-center">
          <div className="inline-flex items-center justify-center size-12 border-2 border-foreground bg-art-blue/10 text-art-blue mb-4">
            <RotateCcw className="size-6 animate-spin" aria-hidden="true" />
          </div>
          <h1 className={`text-3xl sm:text-4xl font-black tracking-tight text-foreground mb-3 ${!submitError ? 'shimmer text-foreground/80' : ''}`}>{t('savingResults')}</h1>
          <p className="text-muted-foreground max-w-[50ch] mx-auto text-sm sm:text-base leading-relaxed mb-6">
            {submitError || t('savingResultsDesc')}
          </p>
          {submitError && (
            <Button
              size="lg"
              className="font-bold text-base px-8 py-3 rounded-none bg-foreground text-background hover:bg-foreground/90"
              onClick={() => {
                void submit(session)
              }}
            >
              {t('retrySubmission')}
            </Button>
          )}
        </section>
      </div>
    )}

    {session.phase === 'complete' && session.receipt && (() => {
      const levelTitles: Record<number, string> = {
        1: t('level1Title'),
        2: t('level2Title'),
        3: t('level3Title'),
        4: t('level4Title'),
        5: t('level5Title'),
      }

      return (
        <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 md:p-8">
          <section className="w-[min(calc(100%-32px),880px)] my-2 mx-auto border-2 border-foreground bg-background shadow-xs overflow-hidden">
            {/* Top architectural banner with completion seal */}
            <div className="flex items-center justify-between px-6 sm:px-8 py-3.5 border-b border-border bg-muted/40">
              <div className="flex items-center gap-2">
                <span className="flex items-center justify-center size-5 bg-art-blue text-white" aria-hidden="true">
                  <Check className="size-3.5 stroke-[3]" />
                </span>
                <span className="text-[11px] font-black uppercase tracking-widest text-muted-foreground">
                  {t('sessionSaved')}
                </span>
              </div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('pycilLearn')}
              </span>
            </div>

            <div className="p-6 sm:p-10 md:p-12">
              <div className="flex items-center gap-3 mb-2">
                <span className="size-3 bg-art-blue" aria-hidden="true" />
                <h1 className="text-3xl sm:text-4xl md:text-5xl font-black tracking-tight text-foreground leading-[1.1] m-0">
                  {t('sessionComplete')}
                </h1>
              </div>

              <p className="text-sm sm:text-base text-muted-foreground max-w-[65ch] leading-relaxed mb-8">
                {t('meaningsReviewed', { count: session.receipt.results.length })}{' '}
                {session.receipt.results.some(result => !result.applied) &&
                  t('olderResultsRetainedCount', {
                    count: session.receipt.results.filter(result => !result.applied).length,
                  })}
              </p>

              {/* FSRS 5-Stage Mastery Staircase */}
              <div className="mb-8">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-black uppercase tracking-widest text-muted-foreground">
                    {t('masteryStaircase')}
                  </span>
                  <span className="text-xs font-bold text-muted-foreground">
                    FSRS v5
                  </span>
                </div>

                <div className="grid grid-cols-5 gap-2 sm:gap-3 border-y-2 border-foreground py-6">
                  {[1, 2, 3, 4, 5].map(level => {
                    const count = session.receipt!.results.filter(result => result.level === level).length
                    const stepHeights = ['h-2', 'h-3.5', 'h-5', 'h-6.5', 'h-8']
                    return (
                      <div
                        key={level}
                        className={`p-3 sm:p-4 border flex flex-col justify-between transition-colors ${
                          count > 0 ? 'border-foreground bg-card' : 'border-border bg-muted/20 text-muted-foreground'
                        }`}
                      >
                        <div className="flex flex-col">
                          <strong className="text-2xl sm:text-4xl font-black tabular-nums text-foreground">
                            {count}
                          </strong>
                          <span className="text-xs font-bold text-foreground mt-1">
                            {t('level', { level })}
                          </span>
                          <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold hidden sm:block mt-0.5">
                            {levelTitles[level]}
                          </span>
                        </div>
                        {/* Visual Bauhaus staircase pedestal */}
                        <div className="mt-4 pt-2 border-t border-border">
                          <div
                            className={`w-full ${stepHeights[level - 1]} ${
                              count > 0 ? 'bg-art-blue' : 'bg-muted/60'
                            }`}
                            aria-hidden="true"
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Detailed Mastery Ledger */}
              <details className="group border border-foreground bg-card mb-8">
                <summary className="flex items-center justify-between p-4 cursor-pointer font-bold select-none hover:bg-muted/40 transition-colors">
                  <div className="flex items-center gap-2.5">
                    <span className="size-2 bg-art-blue" aria-hidden="true" />
                    <span>{t('seeMasteryByMeaning')}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground font-semibold">
                    <span className="px-2 py-0.5 border border-border bg-muted/60">
                      {session.receipt.results.length}
                    </span>
                    <ChevronDown
                      className="size-4 transition-transform duration-200 group-open:rotate-180"
                      aria-hidden="true"
                    />
                  </div>
                </summary>
                <div className="border-t border-border divide-y divide-border">
                  {session.receipt.results.map(result => (
                    <div
                      key={result.sense_id}
                      className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-sm hover:bg-muted/20 transition-colors"
                    >
                      <div className="flex items-baseline gap-2 min-w-0">
                        <span className="font-bold text-foreground text-base truncate">
                          {reviewName(result.sense_id)}
                        </span>
                      </div>
                      <div className="flex items-center flex-wrap gap-3 sm:ml-auto">
                        <strong className="inline-flex items-center px-2 py-0.5 text-xs font-bold border border-border bg-muted/40 text-foreground tabular-nums font-normal">
                          Level {result.level} · Elo {Math.round(result.elo)}
                        </strong>
                        <small className="text-xs text-muted-foreground flex items-center gap-1.5">
                          <span
                            className={`size-1.5 rounded-full ${result.applied ? 'bg-art-blue' : 'bg-muted-foreground'}`}
                            aria-hidden="true"
                          />
                          {result.applied ? t('scheduleUpdated') : t('olderResultRetained')}
                        </small>
                      </div>
                    </div>
                  ))}
                </div>
              </details>

              {/* Footer action */}
              <div className="pt-6 border-t-2 border-foreground flex justify-end">
                <Button
                  asChild
                  size="lg"
                  className="w-full sm:w-auto font-bold text-base px-8 py-3 rounded-none bg-foreground text-background hover:bg-foreground/90 transition-colors cursor-pointer"
                  onClick={() => {
                    discardSession(accountId, nodeId)
                  }}
                >
                  <Link href={backHref}>
                    {tLib('backToLibrary')}
                  </Link>
                </Button>
              </div>
            </div>
          </section>
        </div>
      )
    })()}

      <AlertDialog open={exitDialogOpen} onOpenChange={setExitDialogOpen}>
        <AlertDialogContent className="rounded-none border border-foreground max-w-[440px] p-6 bg-background">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-heading font-extrabold text-xl text-foreground">
              {t('pauseSessionTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-sm text-muted-foreground leading-relaxed mt-2">
              {t('pauseSessionDesc', { pos: session.position + 1, total: session.questions.length, finished })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex flex-col gap-2.5 mt-6">
            <Button
              type="button"
              className="w-full justify-center rounded-none font-bold text-sm bg-foreground text-background hover:bg-foreground/90 cursor-pointer"
              disabled={busy}
              onClick={() => {
                setExitDialogOpen(false)
                if (Object.keys(session.attempts).length > 0) {
                  commit(finishSession(session))
                } else {
                  if (accountId && nodeId) discardSession(accountId, nodeId)
                  router.push(backHref)
                }
              }}
            >
              {t('finishAndSave')}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="w-full justify-center rounded-none font-semibold text-sm border-foreground hover:bg-accent cursor-pointer"
              onClick={() => {
                setExitDialogOpen(false)
                router.push(backHref)
              }}
            >
              {t('pauseAndExit')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full justify-center rounded-none font-medium text-xs text-muted-foreground hover:text-foreground cursor-pointer"
              onClick={() => setExitDialogOpen(false)}
            >
              {t('keepStudying')}
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  )
}
