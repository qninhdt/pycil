'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { PycilBrand, MarkPaths } from '@/components/application/brand'
import { ArrowRight, ArrowDownIcon, ArrowUpRight, Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { LearningMap } from './learning-map'

export function LandingPage() {
  const tLanding = useTranslations('landing')
  const tNav = useTranslations('nav')
  const tHome = useTranslations('home')

  return <div className="mx-auto max-w-[1600px] bg-background text-foreground [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-4 [&_a:focus-visible]:outline-ring [&_button:focus-visible]:outline-2 [&_button:focus-visible]:outline-offset-4 [&_button:focus-visible]:outline-ring">
    <a className="skip-link" href="#landing-content">{tNav('skipToContent')}</a>
    <header className="mx-[4%] flex min-h-24 items-center justify-between gap-6 border-b border-foreground max-md:mx-[6%] max-md:min-h-20 max-md:gap-3">
      <PycilBrand />
      <nav aria-label={tNav('mainNav')} className="flex items-center gap-8 text-[13px] font-semibold [&_>_a:not([data-slot]):hover]:underline [&_>_a]:underline-offset-4 max-[1100px]:gap-5 max-md:gap-4 max-md:[&_>_a:nth-child(-n+2)]:hidden max-md:[&_[data-slot=button]]:px-3 max-[359px]:[&_>_a:nth-child(3)]:hidden">
        <a href="#learning-map">{tLanding('howItWorks')}</a>
        <a href="#library">{tLanding('yourLibrary')}</a>
        <Link href="/login">{tLanding('signIn')}</Link>
        <Button asChild><Link href="/signup">{tLanding('getStarted')} <ArrowUpRight /></Link></Button>
      </nav>
    </header>
    <main id="landing-content" tabIndex={-1}>
      <section className="px-[4%] pt-16 pb-12 max-md:px-[6%] max-md:pt-11 max-md:pb-8" aria-labelledby="landing-title">
        <div className="relative flex items-center justify-between gap-10 [&_h1]:text-[clamp(64px,6.6vw,96px)] [&_h1]:font-extrabold [&_h1]:leading-[1.04] [&_h1]:tracking-[-.04em] [&_h1_span]:text-action-red dark:[&_h1_span]:text-art-yellow max-md:gap-0 max-md:[&_h1]:text-[clamp(38px,9.6vw,64px)] max-md:[&_h1]:leading-[1.08] max-[359px]:[&_h1]:text-[36px]">
          <h1 id="landing-title">{tLanding('heroTitle1')}<br />{tLanding('heroTitle2')}<span>{tLanding('heroTitleHighlight')}</span></h1>
          <svg className="mr-[5%] size-[190px] shrink-0 max-[1100px]:mr-0 max-[1100px]:size-[150px] max-md:hidden" viewBox="0 0 200 200" aria-hidden="true">
            <circle cx="66" cy="59" r="46" fill="var(--art-red)" />
            <path d="M111 4V109H200Z" fill="var(--art-yellow)" />
            <path d="M16 126H111V200H16Z" fill="var(--art-blue)" />
            <path d="M0 109H200M111 0V200" fill="none" stroke="var(--art-ink)" />
          </svg>
        </div>
        <div className="mt-8 flex items-end justify-between gap-6 [&_>_p]:text-[17px] [&_>_p]:leading-[1.7] max-md:mt-6 max-md:block max-md:[&_>_p]:text-sm">
          <p className="whitespace-pre-line">{tLanding('heroSubDesc')}</p>
          <div className="flex items-center gap-7 [&_[data-slot=button]]:min-h-13 [&_[data-slot=button]]:px-6 [&_[data-slot=button]]:text-sm max-[1100px]:gap-4 max-md:mt-6 max-md:flex-col max-md:items-start max-md:gap-2">
            <Button asChild size="lg"><Link href="/signup">{tLanding('buildVocabulary')} <ArrowUpRight /></Link></Button>
            <a className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]" href="#learning-map">{tLanding('tryWordBelow')} <ArrowDownIcon /></a>
          </div>
        </div>
      </section>
      <LearningMap />
      <section id="library" className="mt-[88px] grid grid-cols-2 border-y border-foreground max-md:mt-14 max-md:grid-cols-1" aria-labelledby="library-title">
        <div className="relative min-h-[600px] overflow-hidden border-r border-foreground bg-art-blue px-[8%] py-13 text-[var(--palette-ink)] [&_h2]:relative [&_h2]:z-1 [&_h2]:text-[clamp(40px,4.3vw,64px)] [&_h2]:font-extrabold [&_h2]:leading-[1.06] [&_h2]:tracking-[-.035em] max-[1100px]:min-h-[660px] max-md:min-h-[480px] max-md:border-r-0 max-md:border-b max-md:px-[6%] max-md:py-9 max-md:[&_h2]:text-[42px]">
          <h2 id="library-title" className="whitespace-pre-line">{tLanding('libraryHeading')}</h2>
          <svg className="absolute right-0 bottom-0 max-h-[310px] w-[86%] max-md:max-h-[250px] max-md:w-[82%]" viewBox="0 0 480 350" aria-hidden="true">
            <path d="M0 318H480M88 0V350" stroke="var(--palette-ink)" fill="none" />
            <path d="M88 318V136H270V318Z" fill="var(--palette-canvas)" />
            <path d="M88 136V46H270V136Z" fill="var(--art-yellow)" />
            <path d="M270 136H452V318H270Z" fill="var(--palette-ink)" />
            <circle cx="361" cy="227" r="91" fill="var(--art-red)" />
            <path d="M88 136H270L88 318Z" fill="var(--palette-primary-blue)" />
            <path d="M270 46V318M0 136H480" stroke="var(--palette-ink)" fill="none" />
          </svg>
        </div>
        <div className="px-[10%] py-13 [&_>_p]:max-w-[50ch] [&_>_p]:text-sm [&_>_p]:leading-[1.85] max-[1100px]:px-[8%] max-md:px-[6%] max-md:py-9">
          <p className="!mb-[22px] !text-[26px] !font-[750] !leading-[1.45] !tracking-[-.02em] max-md:!text-[25px] whitespace-pre-line">{tLanding('libraryDesc1')}</p>
          <p>{tLanding('libraryDesc2')}</p>
          <div className="my-8 border-y border-foreground [&_>_div]:flex [&_>_div]:min-h-[62px] [&_>_div]:items-center [&_>_div]:gap-4 [&_>_div]:border-b [&_>_div]:border-border [&_>_div:last-child]:border-b-0 [&_svg]:size-[30px] [&_strong]:text-sm [&_strong]:font-bold [&_span:last-child]:ml-auto [&_span:last-child]:text-[11px] [&_span:last-child]:text-muted-foreground max-md:my-6" aria-label={tLanding('exampleLibrary')}>
            <div className="!min-h-[39px] text-[11px]"><span>{tLanding('exampleLibrary')}</span><span>{tHome('personal')}</span></div>
            <div><Icon name="folder" /><strong>{tLanding('folderReading')}</strong><span>{tLanding('folder')}</span></div>
            <div><Icon name="collection" /><strong>{tLanding('deckWork')}</strong><span>{tLanding('deck')}</span></div>
            <div><Icon name="collection" /><strong>{tLanding('deckPlaces')}</strong><span>{tLanding('deck')}</span></div>
          </div>
          <p>{tLanding('libraryPrivacy')}</p>
          <Link className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]" href="/app/discovery">{tLanding('explorePublishedDecks')} <ArrowUpRight /></Link>
        </div>
      </section>
      <section className="grid grid-cols-2 gap-[8%] px-[4%] py-[104px] max-md:grid-cols-1 max-md:gap-10 max-md:px-[6%] max-md:py-14" aria-labelledby="principles-title">
        <div className="[&_h2]:text-[clamp(36px,3.8vw,56px)] [&_h2]:font-extrabold [&_h2]:leading-[1.13] [&_h2]:tracking-[-.035em] [&_h2_span]:text-action-red dark:[&_h2_span]:text-art-yellow [&_>_p]:mt-[25px] [&_>_p]:text-sm [&_>_p]:leading-[1.7] max-md:[&_h2]:text-[40px] max-md:[&_>_p]:mt-4">
          <h2 id="principles-title">{tLanding('principlesTitle1')}<br />{tLanding('principlesTitle2')}<br /><span>{tLanding('principlesTitle3')}</span></h2>
          <p>{tLanding('principlesSubtitle')}</p>
        </div>
        <div className="[&_article]:flex [&_article]:gap-6 [&_article]:border-t [&_article]:border-foreground [&_article]:py-[25px] [&_article:first-child]:border-t-0 [&_article:first-child]:pt-0 [&_svg]:size-[42px] [&_svg]:shrink-0 [&_h3]:text-[19px] [&_h3]:font-[750] [&_h3]:leading-[1.4] [&_h3]:tracking-[-.015em] [&_p]:mt-[9px] [&_p]:max-w-[50ch] [&_p]:text-[13px] [&_p]:leading-[1.85] [&_p]:text-muted-foreground max-md:[&_article]:gap-[18px] max-md:[&_h3]:text-[17px]">
          <article><Icon name="dictionary" /><div><h3>{tLanding('principle1Title')}</h3><p>{tLanding('principle1Desc')}</p></div></article>
          <article><Icon name="review" /><div><h3>{tLanding('principle2Title')}</h3><p>{tLanding('principle2Desc')}</p></div></article>
          <article><Icon name="robot" /><div><h3>{tLanding('principle3Title')}</h3><p>{tLanding('principle3Desc')}</p></div></article>
        </div>
      </section>
      <section className="relative flex items-center justify-between gap-10 overflow-hidden border-y border-[var(--palette-ink)] bg-art-yellow px-[8%] py-16 text-on-yellow [&_h2]:text-[clamp(56px,5.5vw,80px)] [&_h2]:font-extrabold [&_h2]:leading-[1.05] [&_h2]:tracking-[-.04em] [&_p]:mt-[22px] [&_p]:mb-[30px] [&_p]:text-sm [&_p]:leading-[1.75] [&_[data-slot=button]]:min-h-13 [&_[data-slot=button]]:bg-[var(--palette-ink)] [&_[data-slot=button]]:px-6 [&_[data-slot=button]]:text-sm [&_[data-slot=button]]:text-[var(--palette-canvas)] [&_[data-slot=button]:hover]:bg-[var(--palette-ink-soft)] [&_a:focus-visible]:outline-[var(--palette-ink)] max-md:gap-0 max-md:px-[6%] max-md:py-[42px] max-md:[&_h2]:text-[55px] max-md:[&_p]:max-w-[25ch]" aria-labelledby="closing-title">
        <div><h2 id="closing-title" className="whitespace-pre-line">{tLanding('closingTitle')}</h2><p>{tLanding('closingDesc')}</p>
          <Button asChild size="lg"><Link href="/signup">{tLanding('createYourAccount')} <ArrowUpRight /></Link></Button>
        </div>
        <svg className="mr-[6%] h-[260px] w-[220px] shrink-0 [--art-yellow:var(--palette-canvas)] max-md:absolute max-md:top-[35px] max-md:-right-[22px] max-md:mr-0 max-md:h-[110px] max-md:w-[90px]" viewBox="0 0 312 362" aria-hidden="true"><MarkPaths /></svg>
      </section>
    </main>
    <footer className="flex min-h-[120px] items-center justify-between gap-6 px-[4%] py-6 [&_>_p]:text-xs [&_>_p]:text-muted-foreground max-md:flex-wrap max-md:gap-5 max-md:px-[6%] max-md:py-7 max-md:[&_>_p]:order-3 max-md:[&_>_p]:basis-full"><PycilBrand /><p>{tLanding('footerTagline')}</p><Link className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]" href="/app">{tLanding('openApp')} <ArrowRight /></Link></footer>
  </div>
}
