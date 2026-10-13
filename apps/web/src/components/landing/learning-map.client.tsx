'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { ArrowRight, Check, Icon } from '@/components/artwork/artwork'

export function LearningMap() {
  const t = useTranslations('landing')
  const [meaningIndex, setMeaningIndex] = useState(0)
  const [answer, setAnswer] = useState<string | null>(null)

  const meanings = [
    {
      definition: t('defRiver'),
      deck: t('deckRiver'),
      sentence: t('sentRiver'),
      example: t('exRiver'),
      choices: ['bank', 'branch', 'bridge'],
    },
    {
      definition: t('defMoney'),
      deck: t('deckMoney'),
      sentence: t('sentMoney'),
      example: t('exMoney'),
      choices: ['shop', 'bank', 'park'],
    },
  ]

  const meaning = meanings[meaningIndex]
  const correct = answer === 'bank'

  return <section id="learning-map" className="mx-[4%] border-t border-foreground max-md:mx-[6%]" aria-labelledby="map-title">
    <div className="flex items-center justify-between gap-4 py-5 [&_h2]:text-base [&_h2]:font-[750] [&_>_p]:text-[11px] [&_>_p]:text-muted-foreground max-md:flex-col max-md:items-start max-md:gap-1.5 max-md:[&_h2]:text-[15px]"><h2 id="map-title">{t('mapTitle')}</h2><p>{t('interactiveBadge')}</p></div>
    <div className="grid grid-cols-[1.18fr_1fr_1.18fr_.94fr] border-y border-foreground [&_>_section]:min-w-0 [&_>_section+section]:border-l [&_>_section+section]:border-foreground max-[1100px]:grid-cols-2 max-[1100px]:[&_>_section:nth-child(3)]:border-l-0 max-[1100px]:[&_>_section:nth-child(n+3)]:border-t max-[1100px]:[&_>_section:nth-child(n+3)]:border-foreground max-md:grid-cols-1 max-md:[&_>_section+section]:border-l-0 max-md:[&_>_section+section]:border-t">
      <section aria-labelledby="meaning-title">
        <header className="flex h-[54px] items-center gap-3 border-b border-foreground px-5 [&_>_span]:text-[11px] [&_>_span]:font-bold [&_>_span]:text-muted-foreground [&_>_span]:tabular-nums [&_h3]:text-xs [&_h3]:font-[750] [&_>_svg]:ml-auto [&_>_svg]:size-4 max-md:px-[18px] max-md:[&_>_svg]:rotate-90"><span>{t('step1Number')}</span><h3 id="meaning-title">{t('step1Title')}</h3><ArrowRight /></header>
        <div className="relative min-h-[330px] px-5 py-6 max-[1100px]:min-h-[315px] max-md:min-h-0 max-md:px-[18px] max-md:pb-7">
          <div className="flex flex-col gap-[5px] [&_>_strong]:text-[64px] [&_>_strong]:font-extrabold [&_>_strong]:leading-none [&_>_strong]:tracking-[-.04em] [&_>_strong_>_span]:text-art-red [&_>_span]:text-xs [&_>_span]:text-muted-foreground"><strong>bank<span>.</span></strong><span>/bæŋk/ · noun</span></div>
          <p className="mt-5 mb-3.5 text-xs leading-[1.65] whitespace-pre-line">{t('step1Desc')}</p>
          <div className="flex flex-col gap-2 [&_button]:flex [&_button]:min-h-12 [&_button]:cursor-pointer [&_button]:items-center [&_button]:gap-2.5 [&_button]:border [&_button]:border-border [&_button]:px-2.5 [&_button]:py-2 [&_button]:text-left [&_button]:text-xs [&_button]:leading-normal [&_button]:transition-colors [&_button]:duration-150 [&_button:hover]:border-foreground [&_button[aria-pressed=true]]:border-foreground [&_button[aria-pressed=true]]:bg-[var(--palette-yellow-soft)] max-md:[&_button]:min-h-[50px] max-md:[&_button]:text-[13px]">{meanings.map((item, index) => <button type="button" key={item.deck} aria-pressed={meaningIndex === index} onClick={() => { setMeaningIndex(index); setAnswer(null) }}>
            <span className="grid size-[18px] shrink-0 place-items-center border border-foreground [&_svg]:size-3.5" aria-hidden="true">{meaningIndex === index && <Check />}</span><span>{item.definition}</span>
          </button>)}</div>
        </div>
      </section>
      <section className="bg-[var(--palette-blue-soft)] dark:[--muted-foreground:var(--foreground)] [&_>_div]:max-md:grid [&_>_div]:max-md:grid-cols-[68px_1fr] [&_>_div]:max-md:items-start [&_>_div]:max-md:gap-x-[22px] [&_>_div_>_p]:max-md:col-start-2 [&_>_div_>_p]:max-md:mt-4" aria-labelledby="deck-title">
        <header className="flex h-[54px] items-center gap-3 border-b border-foreground px-5 [&_>_span]:text-[11px] [&_>_span]:font-bold [&_>_span]:text-muted-foreground [&_>_span]:tabular-nums [&_h3]:text-xs [&_h3]:font-[750] [&_>_svg]:ml-auto [&_>_svg]:size-4 max-md:px-[18px] max-md:[&_>_svg]:rotate-90"><span>{t('step2Number')}</span><h3 id="deck-title">{t('step2Title')}</h3><ArrowRight /></header>
        <div className="relative min-h-[330px] px-5 py-6 max-[1100px]:min-h-[315px] max-md:min-h-0 max-md:px-[18px] max-md:pb-7">
          <Icon name="collection" className="mb-[21px] size-[68px] max-md:mb-0" />
          <div aria-live="polite"><div key={meaning.deck} className="animate-in slide-in-from-bottom-1 duration-150 ease-out motion-reduce:animate-none [&_>_p:last-child]:mt-1 [&_>_p:last-child]:text-xs [&_>_p:last-child]:leading-[1.6]"><p className="min-h-14 text-[23px] font-extrabold leading-[1.2] tracking-[-.025em] max-[1100px]:min-h-0">{meaning.deck}</p><p className="mt-3.5 text-[15px] font-[750] [&_span]:text-[11px] [&_span]:font-normal">bank <span>· noun</span></p><p>{meaning.definition}</p></div></div>
          <p className="mt-[25px] text-xs leading-[1.7] text-muted-foreground whitespace-pre-line max-md:[&_br]:hidden">{t('step2Desc')}</p>
        </div>
      </section>
      <section className="[&_>_div_>_p:first-child]:mt-0" aria-labelledby="practice-title">
        <header className="flex h-[54px] items-center gap-3 border-b border-foreground px-5 [&_>_span]:text-[11px] [&_>_span]:font-bold [&_>_span]:text-muted-foreground [&_>_span]:tabular-nums [&_h3]:text-xs [&_h3]:font-[750] [&_>_svg]:ml-auto [&_>_svg]:size-4 max-md:px-[18px] max-md:[&_>_svg]:rotate-90"><span>{t('step3Number')}</span><h3 id="practice-title">{t('step3Title')}</h3><ArrowRight /></header>
        <div className="relative min-h-[330px] px-5 py-6 max-[1100px]:min-h-[315px] max-md:min-h-0 max-md:px-[18px] max-md:pb-7">
          <p className="mt-5 mb-3.5 text-xs leading-[1.65]">{t('step3Desc')}</p>
          <p key={meaning.deck} className="animate-in slide-in-from-bottom-1 duration-150 ease-out motion-reduce:animate-none min-h-[94px] text-[22px] font-[750] leading-normal tracking-[-.02em] max-md:min-h-0 max-md:max-w-[27ch]">{meaning.sentence}</p>
          <div className="mt-[22px] flex flex-wrap gap-1.5 [&_button]:inline-flex [&_button]:min-h-11 [&_button]:cursor-pointer [&_button]:items-center [&_button]:justify-center [&_button]:gap-1 [&_button]:border [&_button]:border-foreground [&_button]:px-3 [&_button]:py-2 [&_button]:text-xs [&_button]:font-semibold [&_button]:transition-colors [&_button]:duration-150 [&_button:hover]:bg-accent [&_button[aria-pressed=true]]:bg-primary [&_button[aria-pressed=true]]:text-primary-foreground [&_svg]:size-3.5" aria-label={t('step3MissingWordAria')}>{meaning.choices.map(choice => <button type="button" key={choice} aria-pressed={answer === choice} onClick={() => setAnswer(choice)}>{choice}{answer === choice && correct && <Check />}</button>)}</div>
          <p className="mt-4 min-h-[60px] text-[11px] leading-[1.7] text-muted-foreground max-md:min-h-10" role="status">{answer === null ? t('step3ChoosePrompt') : correct ? t('step3Correct', { example: meaning.example }) : t('step3Incorrect', { hint: meaning.definition.toLowerCase() })}</p>
        </div>
      </section>
      <section className="[&_>_div]:max-md:min-h-[200px] [&_>_div]:max-md:pr-[110px] [&_>_div_>_p:last-child]:mt-3.5" aria-labelledby="review-title">
        <header className="flex h-[54px] items-center gap-3 border-b border-foreground px-5 [&_>_span]:text-[11px] [&_>_span]:font-bold [&_>_span]:text-muted-foreground [&_>_span]:tabular-nums [&_h3]:text-xs [&_h3]:font-[750] [&_>_svg]:ml-auto [&_>_svg]:size-4 max-md:px-[18px] max-md:[&_>_svg]:rotate-90"><span>{t('step4Number')}</span><h3 id="review-title">{t('step4Title')}</h3></header>
        <div className="relative min-h-[330px] px-5 py-6 max-[1100px]:min-h-[315px] max-md:min-h-0 max-md:px-[18px] max-md:pb-7">
          <div className="relative mx-auto mb-4 h-[130px] w-[170px] [&_>_span]:absolute [&_>_span:first-child]:left-2 [&_>_span:first-child]:top-0 [&_>_span:first-child]:size-28 [&_>_span:first-child]:rounded-full [&_>_span:first-child]:border-[23px] [&_>_span:first-child]:border-art-red [&_>_span:nth-child(2)]:left-[105px] [&_>_span:nth-child(2)]:top-[81px] [&_>_span:nth-child(2)]:size-[45px] [&_>_span:nth-child(2)]:bg-art-blue [&_>_span:last-child]:left-[128px] [&_>_span:last-child]:top-[18px] [&_>_span:last-child]:size-[53px] [&_>_span:last-child]:bg-art-yellow [&_>_span:last-child]:[clip-path:polygon(0_0,100%_100%,0_100%)] max-md:absolute max-md:top-[25px] max-md:right-2.5 max-md:w-[85px] max-md:overflow-hidden max-md:[&_>_span:first-child]:left-0 max-md:[&_>_span:first-child]:size-[74px] max-md:[&_>_span:first-child]:border-16 max-md:[&_>_span:nth-child(2)]:left-12 max-md:[&_>_span:nth-child(2)]:top-[65px] max-md:[&_>_span:nth-child(2)]:size-[30px] max-md:[&_>_span:last-child]:left-12 max-md:[&_>_span:last-child]:top-[103px] max-md:[&_>_span:last-child]:size-[30px]" aria-hidden="true"><span /><span /><span /></div>
          <p className="text-[21px] font-extrabold leading-[1.3] tracking-[-.025em] whitespace-pre-line">{t('step4Heading')}</p>
          <p className="mt-[25px] text-xs leading-[1.7] text-muted-foreground whitespace-pre-line max-md:[&_br]:hidden">{t('step4Desc')}</p>
        </div>
      </section>
    </div>
    <div className="flex justify-between gap-4 py-[18px] text-[11px] [&_>_span]:font-semibold [&_>_p]:text-muted-foreground max-md:flex-col max-md:gap-2 max-md:text-[10px] max-md:leading-[1.6]"><span>{t('mapFooterFlow')}</span><p>{t('mapFooterSub')}</p></div>
  </section>
}
