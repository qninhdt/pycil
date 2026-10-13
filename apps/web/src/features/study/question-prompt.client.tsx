'use client'

import { useEffect, useRef } from 'react'
import { useTranslations } from 'next-intl'
import { MarkedText } from '@/components/content/marked-text'
import type { PreparedQuestion, QuestionOption } from '@/lib/api/study'

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
  if (question.question_type === 'dialogue_completion' && Array.isArray(question.content)) {
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
  if (question.question_type === 'cloze_to_word') {
    const [before, after] = content.split('_')
    const activeWord = item.format === 'single_word' ? typed : selectedOption ? selectedOption.content : ''

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
  if (question.question_type === 'word_to_usage') {
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
  if (question.question_type === 'word_to_definition') {
    return (
      <div className="mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background flex flex-col justify-center w-full">
        <strong className="block text-3xl sm:text-4xl font-black tracking-tight text-foreground leading-tight wrap-anywhere">
          <MarkedText text={content} />
        </strong>
      </div>
    )
  }

  // 5. MEANING_IN_CONTEXT (The Excerpt Monocle)
  if (question.question_type === 'meaning_in_context') {
    return (
      <blockquote className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border border-foreground bg-background">
        <p className="text-base sm:text-lg font-medium leading-relaxed text-foreground m-0">
          <MarkedText text={content} />
        </p>
      </blockquote>
    )
  }

  // 6. DEFINITION_TO_WORD (The Reverse Codex)
  if (question.question_type === 'definition_to_word') {
    return (
      <div className="w-full mb-4 sm:mb-6 p-4 sm:p-6 md:p-7 border-l-4 border-foreground border-y border-r border-foreground bg-background">
        <blockquote className="text-base sm:text-lg font-medium leading-relaxed text-foreground m-0">
          &ldquo;<MarkedText text={content} />&rdquo;
        </blockquote>
      </div>
    )
  }

  // 7. CONTEXT_TO_WORD (The Case Dossier) - Strip "In this situation:" prefix!
  if (question.question_type === 'context_to_word') {
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


