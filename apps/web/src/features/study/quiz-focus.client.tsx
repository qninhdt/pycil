'use client'


import Link from 'next/link'
import { Check, RotateCcw, X } from '@/components/artwork/artwork'
import { GradeDetails } from '@/features/study/grade-details.client'
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
import { DotGridWave } from './dot-grid-wave.client'
import { discardSession, finishSession, startNextRound, type StudySession } from './session'
import { RoundRecap, SessionReceipt } from './session-recap.client'
import { Prompt } from './question-prompt.client'
import { useStudyRuntime } from './use-study-runtime.client'
import { useTranslations } from 'next-intl'

export function QuizFocus({ initialSession }: { initialSession?: StudySession } = {}) {
  const t = useTranslations('learning')
  const tCommon = useTranslations('common')
  const tLib = useTranslations('library')
  const tHome = useTranslations('home')
  const { restart, router, account, params, profile, accountId, nodeId, selection, backHref, session, starting, busy, error, submitError, blocked, selected, setSelected, names, exitDialogOpen, setExitDialogOpen, preparation, item, typed, question, attempt, total, finished, selectedOption, commit, start, answer, next, submit, handleExitClick } = useStudyRuntime(initialSession)

  if (!session || (!initialSession && (account.status !== 'ready' || !profile || session.accountId !== accountId || session.prepared.node_id !== nodeId))) {
    const accountError = account.status === 'error' ? account.error || t('couldNotPrepareSession')
      : account.status === 'signed-out' || account.status === 'task' ? t('signInToStudy') : ''
    const preparationError = error || accountError
    const needsSignIn = account.status === 'signed-out' || account.status === 'task'
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
            <span>{selection === 'due' ? tLib('review') : selection === 'new' ? tLib('learnNew') : tHome('practice')}</span>
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

        <AlertDialog open={Boolean(preparationError)}>
          <AlertDialogContent size="sm" onEscapeKeyDown={() => router.replace(backHref)}>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('couldNotPrepareSession')}</AlertDialogTitle>
              <AlertDialogDescription>{preparationError}</AlertDialogDescription>
            </AlertDialogHeader>
            <div className="flex flex-wrap gap-2">
              {needsSignIn ? <Button asChild><Link href={`/login?returnTo=${encodeURIComponent(`/app/learn?${params}`)}`}>{tCommon('signIn')}</Link></Button>
                : <Button disabled={starting} onClick={() => { if (accountError) account.retry(); else void start() }}>{tCommon('retry')}</Button>}
              <Button variant="outline" onClick={() => router.replace(backHref)}>{tLib('backToLibrary')}</Button>
            </div>
          </AlertDialogContent>
        </AlertDialog>

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
                  preparation.current?.abort()
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
    definition_to_word: t('findTheWord'),
    context_to_word: t('readTheContext'),
    cloze_to_word: t('completeTheSentence'),
    word_to_definition: t('explainTheMeaning'),
    word_to_usage: t('useThisMeaning'),
    dialogue_completion: t('completeTheDialogue'),
    meaning_in_context: t('meaningInContext'),
    sentence_rewrite: t('rewriteTheSentence'),
  }

  // Helper metrics for WORD_TO_USAGE & SENTENCE_REWRITE
  const usageWordCount = typed.trim() ? typed.trim().split(/\s+/).length : 0
  const isUsageQuestion = question?.question_type === 'word_to_usage'
  const isRewriteQuestion = question?.question_type === 'sentence_rewrite'
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
    question?.question_type === 'dialogue_completion' ||
    question?.question_type === 'meaning_in_context' ||
    question?.question_type === 'sentence_rewrite'

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
          <span>{selection === 'due' ? tLib('review') : selection === 'new' ? tLib('learnNew') : tHome('practice')}</span>
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
                  {question!.question_type === 'definition_to_word'
                    ? t('promptWhichWordMatches')
                    : question!.question_type === 'context_to_word'
                      ? t('promptWhichWordFits')
                      : question!.question_type === 'cloze_to_word'
                        ? t('completeTheSentence')
                        : question!.question_type === 'dialogue_completion'
                          ? t('promptChooseBestReply')
                          : question!.question_type === 'meaning_in_context'
                            ? t('promptWhatDoesHighlightedMean')
                            : question!.question_type === 'word_to_definition'
                              ? t('explainTheMeaning')
                              : question!.question_type === 'sentence_rewrite'
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
                      void answer(item.format === 'single_choice' ? selected : typed)
                    }}
                  >
                    {item.format === 'single_choice' ? (
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
                    ) : item.format === 'single_word' ? (
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
                          maxLength={profile?.learning_options.limits.max_answer_chars}
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
                          maxLength={profile?.learning_options.limits.max_answer_chars}
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
                        {item.format === 'single_choice' ? (
                          <span>{t('pressToChooseShortcut', { count: item.options.length })}</span>
                        ) : item.format === 'single_word' ? (
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
                              restart()
                            }}
                          >
                            {t('startNewSession')}
                          </Button>
                        ) : item.format === 'single_choice' ? (
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
                      {question!.question_type === 'sentence_rewrite' && attempt.answer && (
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
                  item.format === 'single_choice' ? (
                    <span className="flex items-center gap-1.5 font-mono text-[11px]">
                      <kbd className="px-1.5 py-0.5 border border-foreground/30 bg-muted/60 font-bold text-foreground">1–{item.options.length}</kbd>
                      <span>{t('selectOptionAria')}</span>
                    </span>
                  ) : item.format === 'single_word' ? (
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

      {session.phase === 'recap' && <RoundRecap error={error} session={session} clearedThisRound={clearedThisRound} reviewName={reviewName} onContinue={() => commit(startNextRound(session))} />}

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

    {session.phase === 'complete' && session.receipt && <SessionReceipt receipt={session.receipt} reviewName={reviewName} backHref={backHref} onExit={() => discardSession(accountId, nodeId)} />}

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
