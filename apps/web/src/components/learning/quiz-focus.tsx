'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, ArrowRight, Check, RotateCcw, X } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { Background } from '@/components/artwork/artwork'
import { MarkedText } from '@/components/content/marked-text'
import { Button } from '@/components/ui/button'
import { flashcardArtwork } from '@/lib/flashcard-artwork'
import { useServices } from '@/lib/services/provider'
import { advanceSession, allQuestions, completedCount, createStudySession, currentQuestion, discardSession, loadSession, recordAttempt, saveSession, sessionKey, startNextRound, type StudySession } from '@/lib/study-session'
import { HomeApiError, type GradeResult, type PreparedQuestion, type SessionSelection } from '@/lib/home-api'
import { libraryHref, publishedHref } from '@/lib/library-model'

const labels: Record<string, string> = {
  DEFINITION_TO_WORD: 'Find the word', CONTEXT_TO_WORD: 'Read the context', CLOZE_TO_WORD: 'Complete the sentence',
  WORD_TO_DEFINITION: 'Explain the meaning', WORD_TO_USAGE: 'Use this meaning', DIALOGUE_COMPLETION: 'Complete the dialogue',
  MEANING_IN_CONTEXT: 'Meaning in context',
}
const formatLabel: Record<string, string> = { SINGLE_CHOICE: 'Choose one', SINGLE_WORD: 'Type one word', SHORT_ANSWER: 'Write a short answer' }
const ratingReason = { AGAIN: 'A question stayed unclear or most first answers missed', HARD: 'Recovered after a retry or a partial answer',
  GOOD: 'Cleared the questions on the first try', EASY: 'Cleared varied or advanced questions on the first try' }

function Prompt({ item }: { item: PreparedQuestion }) {
  const { question } = item
  if (question.question_type === 'DIALOGUE_COMPLETION' && Array.isArray(question.content)) return <div className="grid gap-3 max-w-[620px] mb-7.5" aria-label="Dialogue">
    {question.content.map((turn, index) => <div className="grid grid-cols-[80px_minmax(0,1fr)] items-start gap-3 [&_p]:w-fit [&_p]:max-w-full [&_p]:px-4 [&_p]:py-3 [&_p]:border [&_p]:border-border [&_p]:bg-background [&_p]:text-base [&_p]:leading-relaxed [&[data-empty=true]_p]:border-dashed [&[data-empty=true]_p]:text-muted-foreground max-[760px]:grid-cols-[55px_minmax(0,1fr)] max-[760px]:gap-1.5" key={index} data-empty={turn.text === null}>
      <span className="pt-3 text-muted-foreground text-xs font-bold max-[760px]:text-[10px]">{turn.speaker}</span><p>{turn.text === null ? 'Your reply goes here' : <MarkedText text={turn.text} />}</p>
    </div>)}
  </div>
  const content = typeof question.content === 'string' ? question.content : ''
  if (question.question_type === 'CLOZE_TO_WORD') {
    const [before, after] = content.split('_')
    return <p className="max-w-[42ch] mb-8 pl-6 border-l border-foreground text-[clamp(21px,2.6vw,30px)] font-medium leading-normal text-pretty"><MarkedText text={before} /><span className="inline-block min-w-[4ch] px-2 border-b-2 border-art-blue text-muted-foreground text-[0.7em] text-center" aria-label="Missing word">{item.format === 'SINGLE_WORD' ? 'your word' : '…'}</span><MarkedText text={after ?? ''} /></p>
  }
  if (question.question_type === 'WORD_TO_USAGE') {
    const [word, meaning] = content.split(' — ')
    return <div className="mb-7.5 [&_strong]:block [&_strong]:text-[clamp(34px,4vw,58px)] [&_strong]:font-extrabold [&_strong]:tracking-tight [&_strong]:leading-[1.1] [&_strong]:wrap-anywhere [&_p]:mt-3 [&_p]:text-lg [&_p]:text-muted-foreground [&_p]:leading-normal pl-6 border-l-4 border-art-blue"><strong><MarkedText text={word} /></strong><p>{meaning}</p></div>
  }
  if (question.question_type === 'WORD_TO_DEFINITION') return <div className="mb-7.5 [&_strong]:block [&_strong]:text-[clamp(40px,5vw,70px)] [&_strong]:font-extrabold [&_strong]:tracking-tight [&_strong]:leading-[1.1] [&_strong]:wrap-anywhere [&_p]:mt-3 [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:leading-normal [&_p]:tracking-wider [&_p]:uppercase"><strong><MarkedText text={content} /></strong><p>What does this word mean?</p></div>
  if (question.question_type === 'MEANING_IN_CONTEXT') return <blockquote className="max-w-[660px] mb-8 px-7 py-6 border border-foreground bg-background [&_span]:block [&_span]:mb-4 [&_span]:text-muted-foreground [&_span]:text-[11px] [&_span]:font-bold [&_span]:tracking-wider [&_span]:uppercase [&_p]:text-[clamp(20px,2.4vw,29px)] [&_p]:font-medium [&_p]:leading-normal"><span>In this sentence</span><p><MarkedText text={content} /></p></blockquote>
  return <p className={question.question_type === 'DEFINITION_TO_WORD' ? 'max-w-[28ch] mb-8 pl-6 border-l border-foreground text-[clamp(21px,2.6vw,30px)] font-medium leading-normal text-pretty' : 'max-w-[48ch] mb-8 pl-6 border-l border-foreground text-[clamp(19px,2vw,25px)] font-medium leading-normal text-pretty'}><MarkedText text={content} /></p>
}

function GradeDetails({ grade }: { grade: GradeResult | null }) {
  if (!grade) return null
  return <dl className="flex flex-wrap gap-x-4.5 gap-y-2 mt-3 text-xs [&_div]:flex [&_div]:gap-1.5 [&_dt]:text-muted-foreground [&_dt]:capitalize">{Object.entries(grade).filter(([key]) => key !== 'sense_id').map(([key, value]) =>
    <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value === null ? 'Not assessed' : typeof value === 'boolean' ? value ? 'Yes' : 'No' : String(value).replaceAll('_', ' ').toLowerCase()}</dd></div>)}</dl>
}

export function QuizFocus() {
  const account = useAccount(), { services } = useServices(), params = useSearchParams()
  const profile = account.profile, accountId = profile?.id ?? ''
  const nodeId = params.get('node') || profile?.library_node_id || ''
  const selection = (params.get('selection') === 'NEW' || params.get('selection') === 'DUE' ? params.get('selection') : 'AUTO') as SessionSelection
  const backHref = params.get('owner') && nodeId ? publishedHref(params.get('owner')!, nodeId) : libraryHref(nodeId)
  const [session, setSession] = useState<StudySession | null>(null)
  const [hydrated, setHydrated] = useState(false), [starting, setStarting] = useState(false), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [submitError, setSubmitError] = useState(''), [blocked, setBlocked] = useState(false)
  const [selected, setSelected] = useState('')
  const [names, setNames] = useState<Record<number, string>>({})
  const submitting = useRef(false)
  const lastSaved = useRef<string | null>(null)
  const prepared = session?.prepared

  useEffect(() => {
    if (!accountId) return
    lastSaved.current = localStorage.getItem(sessionKey(accountId))
    setSession(loadSession(accountId)); setBlocked(false); setHydrated(true)
  }, [accountId])
  const commit = useCallback((next: StudySession) => {
    try {
      if (localStorage.getItem(sessionKey(next.accountId)) !== lastSaved.current) {
        setError('This session changed in another tab. Reload to continue from the latest answer.'); return false
      }
      saveSession(next); lastSaved.current = localStorage.getItem(sessionKey(next.accountId))
      setSession(next); setError(''); return true
    }
    catch { setError('This browser cannot save the session. Free storage space and retry.'); return false }
  }, [])
  useEffect(() => {
    if (!prepared || !services.dictionary.previews) return
    const ids = [...new Set(prepared.bundles.map(bundle => bundle.sense.word_id))]
    const controller = new AbortController()
    Promise.all(Array.from({ length: Math.ceil(ids.length / 30) }, (_, index) => services.dictionary.previews(ids.slice(index * 30, index * 30 + 30), controller.signal)))
      .then(groups => setNames(Object.fromEntries(groups.flat().map(word => [word.word_id, word.lemma])))).catch(() => {})
    return () => controller.abort()
  }, [prepared, services.dictionary])
  async function start() {
    if (!profile || starting || !nodeId) return
    setStarting(true); setError(''); setBlocked(false)
    try {
      const prepared = await services.learning.prepare({ node_id: nodeId, selection }, new AbortController().signal)
      if (!prepared.bundles.length) { setError('No eligible questions are available for this selection. Try another mode or a smaller scope.'); return }
      commit(createStudySession(profile.id, prepared))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not prepare the session.') }
    finally { setStarting(false) }
  }
  const item = session ? currentQuestion(session) : null
  const phase = session?.phase
  const typed = session?.draft ?? ''
  const question = item?.question
  const attempt = question ? session?.attempts[question.id]?.at(-1) : null
  const total = session?.prepared.actual_question_count ?? 0
  const finished = session ? completedCount(session) : 0

  async function answer(value: string, unknown = false) {
    if (!session || !item || busy || blocked) return
    if (localStorage.getItem(sessionKey(accountId)) !== lastSaved.current) { setError('This session changed in another tab. Reload to continue from the latest answer.'); return }
    if (!value.trim() && !unknown) { setError('Choose or enter an answer.'); return }
    setBusy(true); setError('')
    try {
      const grade = item.format === 'SINGLE_CHOICE' || unknown ? null : await services.learning.grade({ question_id: question!.id, format: item.format, answer: value }, new AbortController().signal)
      commit(recordAttempt(session, value, grade, unknown))
    } catch (cause) {
      if (cause instanceof HomeApiError && (cause.code === 'advanced_grading_not_available' || cause.code === 'question_not_found' || cause.code === 'unsupported_question_format')) {
        setBlocked(true); setError('This question can no longer be graded with your current plan or question bank. Start a new session to use current settings.')
      } else setError(cause instanceof Error ? cause.message : 'Could not check this answer. Retry when connected.')
    }
    finally { setBusy(false) }
  }
  function next() {
    if (!session) return
    if (commit(advanceSession(session))) setSelected('')
  }
  const submit = useCallback(async (current: StudySession) => {
    if (!current.submission || submitting.current) return
    submitting.current = true; setSubmitError('')
    try {
      const receipt = await services.learning.review(current.submission, new AbortController().signal)
      const expected = new Map(current.submission.results.map(result => [result.sense_id, result.rating]))
      if (receipt.results.length !== expected.size || receipt.results.some(result => expected.get(result.sense_id) !== result.rating)) throw new HomeApiError(502, 'invalid_response')
      if (!commit({ ...current, receipt, phase: 'complete' })) setSubmitError('Results were accepted, but this tab could not save the confirmation. Reload or free browser storage, then retry the same submission.')
    } catch (cause) { setSubmitError(cause instanceof Error ? cause.message : 'Results could not be confirmed. Retry the same submission.') }
    finally { submitting.current = false }
  }, [commit, services.learning])
  useEffect(() => { if (session?.phase === 'submitting' && !session.receipt) void submit(session) }, [session, submit])
  useEffect(() => {
    if (phase !== 'question' || !item || item.format !== 'SINGLE_CHOICE') return
    const key = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      const index = Number(event.key) - 1
      if (index >= 0 && index < item.options.length) { event.preventDefault(); setSelected(item.options[index].id) }
    }
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key)
  }, [phase, item])

  if (account.status !== 'ready' || !profile) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Learn</h1><p>{account.status === 'loading' ? 'Loading your account…' : 'Sign in to study your material.'}</p><Button asChild><Link href="/login">Sign in</Link></Button></main>
  if (session && session.accountId !== accountId) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Learn</h1><p>Restoring your session…</p></main>
  if (!hydrated) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Learn</h1><p>Restoring your session…</p></main>
  if (!session || session.phase === 'complete' && (session.prepared.node_id !== nodeId || session.prepared.selection !== selection)) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><Link className="inline-flex items-center gap-2 text-[13px] underline underline-offset-4" href={backHref}><ArrowLeft aria-hidden="true" /> Back to Library</Link>
    <h1>{selection === 'DUE' ? 'Review' : selection === 'NEW' ? 'Learn new' : 'Practice'}</h1>
    <p>Questions are prepared from your learning settings. Your progress is saved on this device.</p>
    {error && <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">{error}</p>}
    <Button onClick={() => { void start() }} disabled={starting}>{starting ? 'Preparing questions…' : 'Start session'} <ArrowRight aria-hidden="true" /></Button>
  </main>
  if (session.prepared.node_id !== nodeId || session.prepared.selection !== selection) return <main className="min-h-svh max-w-[680px] flex flex-col items-start justify-center gap-5 m-auto p-8 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.1] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_p]:max-w-[52ch] [&_p]:leading-relaxed [&_p]:text-muted-foreground"><h1>Session in progress</h1><p>You have an unfinished session with a different Library scope or learning selection.</p>
    <div className="flex flex-wrap gap-2.5"><Button onClick={() => { window.location.href = `/focus/learn?node=${encodeURIComponent(session.prepared.node_id)}&selection=${session.prepared.selection}` }}>Resume session</Button>
      <Button variant="outline" onClick={() => { discardSession(accountId); lastSaved.current = null; setSession(null) }}>Discard and start here</Button></div></main>
  const clearedThisRound = session.questions.filter(id => session.attempts[id]?.at(-1)?.outcome === 'clear').length
  const reviewName = (senseId: number) => { const bundle = session.prepared.bundles.find(value => value.sense.id === senseId); return bundle ? names[bundle.sense.word_id] ?? bundle.sense.definition?.content ?? `Meaning ${senseId}` : `Meaning ${senseId}` }
  return <main className="min-h-svh bg-background text-foreground">
    <header className="h-[78px] grid grid-cols-[78px_minmax(120px,1fr)_minmax(190px,420px)_minmax(120px,1fr)] items-center border-b border-foreground [&_>_a]:grid [&_>_a]:place-items-center [&_>_a]:h-full [&_>_a]:border-r [&_>_a]:border-foreground [&_>_a:hover]:bg-accent [&_>_a_svg]:size-6 max-[760px]:h-16 max-[760px]:grid-cols-[56px_minmax(0,1fr)_120px]"><Link href={backHref} aria-label="Exit learning mode" title="Your session is saved"><X aria-hidden="true" /></Link>
      <div className="flex gap-3 items-baseline min-w-0 px-6 whitespace-nowrap overflow-hidden text-ellipsis [&_strong]:font-extrabold [&_span]:text-muted-foreground max-[760px]:px-3 max-[760px]:gap-2 max-[760px]:text-[13px] max-[760px]:[&_strong]:overflow-hidden max-[760px]:[&_strong]:text-ellipsis"><strong>Pycil Learn</strong><span>{selection === 'DUE' ? 'Review' : selection === 'NEW' ? 'Learn new' : 'Practice'}</span></div>
      <div className="flex items-center gap-4 min-w-0 [&_small]:flex-none [&_small]:text-xs [&_small]:text-muted-foreground [&_small]:tabular-nums max-[760px]:pr-3 max-[760px]:gap-1.5 max-[760px]:overflow-hidden"><div className="w-full h-2 bg-muted overflow-hidden [&_span]:block [&_span]:h-full [&_span]:bg-foreground [&_span]:transition-[width] [&_span]:duration-200 [&_span]:ease-out max-[760px]:min-w-[18px] motion-reduce:[&_span]:transition-none"><span style={{ width: `${total ? finished / total * 100 : 0}%` }} /></div><small className="max-[760px]:hidden">{finished} / {total} finished{session.retry.length ? ` · ${session.retry.length} to retry` : ''}</small><small className="hidden max-[760px]:block max-[760px]:text-[11px]">{finished}/{total}</small></div>
      <span className="px-6 text-right text-[13px] tabular-nums max-[760px]:hidden">{session.phase === 'question' || session.phase === 'feedback' ? `Round ${session.round} · ${session.position + 1}/${session.questions.length}` : `Round ${session.round}`}</span>
    </header>
    {session.phase === 'question' || session.phase === 'feedback' ? item && <div className="grid place-items-center px-6 pt-[clamp(26px,5vh,64px)] pb-5 min-h-[calc(100svh-78px)] bg-background max-[760px]:min-h-[calc(100svh-64px)] max-[760px]:p-3"><article className="focus-card isolate relative w-[min(100%,1120px)] min-h-[min(670px,calc(100svh-160px))] flex items-stretch overflow-hidden border border-foreground bg-background [&_h1]:max-w-[25ch] [&_h1]:mb-7 [&_h1]:text-[clamp(27px,3vw,40px)] [&_h1]:leading-[1.18] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h1]:text-balance max-[760px]:min-h-[calc(100svh-110px)]">
      <div className="absolute inset-0 -z-[1] pointer-events-none [&_>_svg]:w-full [&_>_svg]:h-full after:content-[''] after:absolute after:inset-0 after:bg-[color-mix(in_srgb,var(--background)_82%,transparent)]" aria-hidden="true"><Background name={flashcardArtwork(`${session.seed}:${question!.id}`)} /></div>
      <div className="focus-card-body w-[min(100%,830px)] m-auto p-[clamp(32px,5vw,64px)] max-[760px]:my-0 max-[760px]:mx-auto max-[760px]:px-5.5 max-[760px]:py-7"><span className="inline-flex items-center gap-2.5 mb-6 text-muted-foreground text-[11px] font-bold tracking-widest uppercase [&_i]:block [&_i]:size-[3px] [&_i]:rounded-full [&_i]:bg-current">{labels[question!.question_type]} <i /> {formatLabel[item.format]}</span>
        <h1>{question!.question_type === 'DEFINITION_TO_WORD' ? 'Which word matches this meaning?' : question!.question_type === 'CONTEXT_TO_WORD' ? 'Which word fits this context?' : question!.question_type === 'CLOZE_TO_WORD' ? 'Complete the sentence' : question!.question_type === 'DIALOGUE_COMPLETION' ? 'Choose the best reply' : question!.question_type === 'MEANING_IN_CONTEXT' ? 'What does the highlighted word mean here?' : labels[question!.question_type]}</h1>
        <Prompt item={item} />
        {session.phase === 'question' && <form className="focus-answer" onSubmit={event => { event.preventDefault(); void answer(item.format === 'SINGLE_CHOICE' ? selected : typed) }}>
          {item.format === 'SINGLE_CHOICE' ? <fieldset><legend className="sr-only">Choose one answer</legend><div className="focus-options grid grid-cols-2 gap-2.5 [&_button]:min-h-[68px] [&_button]:flex [&_button]:items-center [&_button]:gap-3.5 [&_button]:px-4 [&_button]:py-3.5 [&_button]:border [&_button]:border-foreground [&_button]:bg-background [&_button]:text-left [&_button]:leading-snug [&_button]:transition-colors [&_button]:duration-150 [&_button:hover]:bg-accent [&_button[aria-pressed=true]]:bg-[color-mix(in_srgb,var(--art-blue)_17%,var(--background))] [&_button[aria-pressed=true]]:border-art-blue [&_button_>_span:first-child]:grid [&_button_>_span:first-child]:place-items-center [&_button_>_span:first-child]:size-7 [&_button_>_span:first-child]:flex-none [&_button_>_span:first-child]:bg-muted [&_button_>_span:first-child]:rounded-full [&_button_>_span:first-child]:font-bold [&_button_>_span:first-child]:tabular-nums max-[760px]:grid-cols-1 max-[760px]:[&_button]:min-h-14 motion-reduce:[&_button]:transition-none">{item.options.map((option, index) =>
            <button key={option.id} type="button" aria-pressed={selected === option.id} onClick={() => setSelected(option.id)}><span>{index + 1}</span><MarkedText text={option.content} /></button>)}</div></fieldset>
            : item.format === 'SINGLE_WORD' ? <label className="grid gap-2 text-xs font-bold uppercase tracking-wider [&_input]:w-full [&_input]:px-4.5 [&_input]:py-4 [&_input]:border [&_input]:border-foreground [&_input]:bg-background [&_input]:text-foreground [&_input]:outline-none [&_input]:text-xl [&_input]:font-medium [&_input]:tracking-normal [&_input]:normal-case [&_input]:resize-y [&_textarea]:w-full [&_textarea]:px-4.5 [&_textarea]:py-4 [&_textarea]:border [&_textarea]:border-foreground [&_textarea]:bg-background [&_textarea]:text-foreground [&_textarea]:outline-none [&_textarea]:text-xl [&_textarea]:font-medium [&_textarea]:tracking-normal [&_textarea]:normal-case [&_textarea]:resize-y [&_input:focus]:border-art-blue [&_input:focus]:ring-1 [&_input:focus]:ring-art-blue [&_textarea:focus]:border-art-blue [&_textarea:focus]:ring-1 [&_textarea:focus]:ring-art-blue">Your word<input autoComplete="off" autoFocus value={typed} onChange={event => { if (session) commit({ ...session, draft: event.target.value }) }} maxLength={8000} /></label>
              : <label className="grid gap-2 text-xs font-bold uppercase tracking-wider [&_input]:w-full [&_input]:px-4.5 [&_input]:py-4 [&_input]:border [&_input]:border-foreground [&_input]:bg-background [&_input]:text-foreground [&_input]:outline-none [&_input]:text-xl [&_input]:font-medium [&_input]:tracking-normal [&_input]:normal-case [&_input]:resize-y [&_textarea]:w-full [&_textarea]:px-4.5 [&_textarea]:py-4 [&_textarea]:border [&_textarea]:border-foreground [&_textarea]:bg-background [&_textarea]:text-foreground [&_textarea]:outline-none [&_textarea]:text-xl [&_textarea]:font-medium [&_textarea]:tracking-normal [&_textarea]:normal-case [&_textarea]:resize-y [&_input:focus]:border-art-blue [&_input:focus]:ring-1 [&_input:focus]:ring-art-blue [&_textarea:focus]:border-art-blue [&_textarea:focus]:ring-1 [&_textarea:focus]:ring-art-blue">Your answer<textarea autoFocus value={typed} onChange={event => { if (session) commit({ ...session, draft: event.target.value }) }} maxLength={8000} rows={4} /></label>}
          {error && <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">{error}</p>}
          <div className="flex justify-end gap-3 mt-6 border-t border-border pt-5.5 [&_button]:min-h-11">{blocked ? <Button type="button" onClick={() => { discardSession(accountId); lastSaved.current = null; setSession(null); setBlocked(false) }}>Start a new session <ArrowRight aria-hidden="true" /></Button>
            : <><Button type="button" variant="outline" onClick={() => { void answer('', true) }} disabled={busy}>I don’t know</Button>
              <Button type="submit" disabled={busy || !(item.format === 'SINGLE_CHOICE' ? selected : typed.trim())}>{busy ? 'Checking…' : 'Check answer'} <ArrowRight aria-hidden="true" /></Button></>}</div>
        </form>}
        {session.phase === 'feedback' && attempt && <div className="focus-feedback flex items-end justify-between gap-6 mt-5.5 p-6 border border-foreground bg-background data-[outcome=clear]:border-art-blue data-[outcome=miss]:border-art-red data-[outcome=partial]:border-art-yellow [&_strong]:block [&_strong]:mb-1.5 [&_strong]:text-xl [&_strong]:font-extrabold [&_p]:mt-1.5 [&_p]:leading-relaxed [&_button]:flex-none max-[760px]:flex-col max-[760px]:items-stretch max-[760px]:p-4" data-outcome={attempt.outcome} role="status"><div><strong>{attempt.outcome === 'clear' ? 'That fits.' : attempt.outcome === 'partial' ? 'Almost there.' : 'Try this again next round.'}</strong>
          <p>Answer: <MarkedText text={question!.correct.content} /></p>
          {session.prepared.preferences.show_explanations && <><p>{question!.correct.explanation}</p><GradeDetails grade={attempt.grade} /></>}{error && <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">{error}</p>}</div>
          <Button onClick={next}>Continue <ArrowRight aria-hidden="true" /></Button></div>}
      </div></article><p className="self-start w-[min(100%,1120px)] mt-4 mb-0 mx-auto text-[11px] text-muted-foreground max-[760px]:hidden">{item.format === 'SINGLE_CHOICE' ? 'Press 1–4 to select an option. ' : ''}Your work is saved as you go.</p></div> : null}
    {session.phase === 'recap' && <section className="w-[min(calc(100%-40px),920px)] my-[clamp(40px,9vh,100px)] mx-auto p-[clamp(24px,4vw,60px)] border border-foreground bg-background [&_h1]:my-4 [&_h1]:mb-7 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.15] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_>_p]:max-w-[60ch] [&_>_p]:leading-relaxed [&_>_p]:mb-6 max-[760px]:w-[calc(100%-24px)] max-[760px]:my-3 max-[760px]:mx-auto max-[760px]:min-h-[calc(100svh-90px)]"><span className="text-[11px] font-extrabold text-muted-foreground uppercase tracking-widest">Round {session.round}</span><h1>{session.retry.length ? 'Ready for another pass.' : 'Round complete.'}</h1>
      <div className="grid grid-cols-2 border-y border-foreground mb-6 [&_p]:flex [&_p]:items-baseline [&_p]:gap-3 [&_p]:py-5 [&_p_+_p]:border-l [&_p_+_p]:border-border [&_p_+_p]:pl-6 [&_strong]:text-[clamp(32px,4vw,48px)] [&_strong]:font-extrabold [&_strong]:tabular-nums [&_span]:text-sm [&_span]:text-muted-foreground"><p><strong>{clearedThisRound}</strong><span>cleared this round</span></p><p><strong>{session.retry.length}</strong><span>returning next round</span></p></div>
      {session.retry.length > 0 && <div className="mb-6.5 [&_h2]:text-base [&_h2]:font-extrabold [&_h2]:mb-2.5 [&_li]:flex [&_li]:flex-wrap [&_li]:items-baseline [&_li]:gap-2.5 [&_li]:py-3 [&_li]:border-b [&_li]:border-border [&_li_span]:font-bold [&_li_small]:text-muted-foreground"><h2>Review before continuing</h2><ul>{session.retry.map(id => {
        const entry = allQuestions(session).find(item => item.question.id === id), last = session.attempts[id]?.at(-1)
        return <li key={id}><span>{entry ? reviewName(entry.question.sense_id) : `Question ${id}`}</span><small>{last?.outcome === 'partial' ? 'Close, but not complete' : 'Needs another pass'}</small></li>
      })}</ul></div>}
      {error && <p className="mt-4 text-art-red text-[13px] font-semibold" role="alert">{error}</p>}
      <Button onClick={() => { commit(startNextRound(session)) }}>Continue to round {session.round + 1} <ArrowRight aria-hidden="true" /></Button>
    </section>}
    {session.phase === 'submitting' && <section className="w-[min(calc(100%-40px),920px)] my-[clamp(40px,9vh,100px)] mx-auto p-[clamp(24px,4vw,60px)] border border-foreground bg-background [&_h1]:my-4 [&_h1]:mb-7 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.15] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_>_p]:max-w-[60ch] [&_>_p]:leading-relaxed [&_>_p]:mb-6 max-[760px]:w-[calc(100%-24px)] max-[760px]:my-3 max-[760px]:mx-auto max-[760px]:min-h-[calc(100svh-90px)]"><RotateCcw className="size-8 text-art-blue" aria-hidden="true" /><h1>Saving your results</h1><p>{submitError || 'Your answers are complete. We’re confirming the update to your review schedule.'}</p>
      {submitError && <Button onClick={() => { void submit(session) }}>Retry the same submission</Button>}</section>}
    {session.phase === 'complete' && session.receipt && <section className="w-[min(calc(100%-40px),920px)] my-[clamp(40px,9vh,100px)] mx-auto p-[clamp(24px,4vw,60px)] border border-foreground bg-background [&_h1]:my-4 [&_h1]:mb-7 [&_h1]:text-[clamp(32px,4vw,54px)] [&_h1]:leading-[1.15] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_>_p]:max-w-[60ch] [&_>_p]:leading-relaxed [&_>_p]:mb-6 max-[760px]:w-[calc(100%-24px)] max-[760px]:my-3 max-[760px]:mx-auto max-[760px]:min-h-[calc(100svh-90px)]"><Check className="size-8 text-art-blue" aria-hidden="true" /><h1>Session complete.</h1>
      <p>{session.receipt.results.length} {session.receipt.results.length === 1 ? 'meaning' : 'meanings'} reviewed. {session.receipt.results.some(result => !result.applied) && `${session.receipt.results.filter(result => !result.applied).length} early practice results kept their previous due dates.`}</p>
      <div className="grid grid-cols-4 border-y border-foreground mb-6 [&_div]:flex [&_div]:flex-col [&_div]:items-baseline [&_div]:py-5 [&_div_+_div]:border-l [&_div_+_div]:border-border [&_div_+_div]:pl-6 [&_strong]:text-[clamp(32px,4vw,48px)] [&_strong]:font-extrabold [&_strong]:tabular-nums [&_span]:text-sm [&_span]:text-muted-foreground max-[760px]:grid-cols-2 max-[760px]:[&_div:nth-child(3)]:border-l-0 max-[760px]:[&_div:nth-child(3)]:pl-0">{(['AGAIN','HARD','GOOD','EASY'] as const).map(rating => <div key={rating}><strong>{session.receipt!.results.filter(result => result.rating === rating).length}</strong><span>{rating.toLowerCase()}</span></div>)}</div>
      <details className="[&_li]:flex [&_li]:flex-wrap [&_li]:items-baseline [&_li]:gap-2.5 [&_li]:py-3 [&_li]:border-b [&_li]:border-border [&_li_span]:font-bold [&_li_small]:text-muted-foreground mb-6 [&_summary]:cursor-pointer [&_summary]:font-bold [&_summary]:py-2.5 [&_li_strong]:ml-auto [&_li_strong]:capitalize"><summary>See ratings by meaning</summary><ul>{session.receipt.results.map(result => <li key={result.sense_id}><span>{reviewName(result.sense_id)}</span><strong>{result.rating.toLowerCase()}</strong><small>{ratingReason[result.rating]} · {result.applied ? 'Review schedule updated' : 'Early practice · date unchanged'}</small></li>)}</ul></details>
      <Button asChild onClick={() => { discardSession(accountId) }}><Link href={backHref}>Back to Library <ArrowRight aria-hidden="true" /></Link></Button>
    </section>}
  </main>
}
