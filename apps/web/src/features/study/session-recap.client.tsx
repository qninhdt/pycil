'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { ChevronDown, Check } from '@/components/artwork/artwork'
import { allQuestions, type StudySession } from './session'

type RecapProps = { error: string; session: StudySession; clearedThisRound: number; reviewName: (id: number) => string; onContinue: () => void }
export function RoundRecap({ error, session, clearedThisRound, reviewName, onContinue }: RecapProps) {
  const t = useTranslations('learning')
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
                    onContinue()
                  }}
                >
                  {t('continueToRound', { round: session.round + 1 })}
                </Button>
              </div>
            </div>
          </section>
        </div>
      )
}

type ReceiptProps = { receipt: NonNullable<StudySession['receipt']>; reviewName: (id: number) => string; backHref: string; onExit: () => void }
export function SessionReceipt({ receipt, reviewName, backHref, onExit }: ReceiptProps) {
  const t = useTranslations('learning')
  const tLib = useTranslations('library')
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
                {t('meaningsReviewed', { count: receipt.results.length })}{' '}
                {receipt.results.some(result => !result.applied) &&
                  t('olderResultsRetainedCount', {
                    count: receipt.results.filter(result => !result.applied).length,
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
                    const count = receipt.results.filter(result => result.level === level).length
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
                      {receipt.results.length}
                    </span>
                    <ChevronDown
                      className="size-4 transition-transform duration-200 group-open:rotate-180"
                      aria-hidden="true"
                    />
                  </div>
                </summary>
                <div className="border-t border-border divide-y divide-border">
                  {receipt.results.map(result => (
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
                    onExit()
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
}
