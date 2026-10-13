import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { ArrowDownIcon, ArrowUpRight } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'

export async function LandingHero() {
  const tLanding = await getTranslations('landing')

  return (
    <section className="px-[4%] pt-16 pb-12 max-md:px-[6%] max-md:pt-11 max-md:pb-8" aria-labelledby="landing-title">
      <div className="relative flex items-center justify-between gap-10 [&_h1]:text-[clamp(64px,6.6vw,96px)] [&_h1]:font-extrabold [&_h1]:leading-[1.04] [&_h1]:tracking-[-.04em] [&_h1_span]:text-action-red dark:[&_h1_span]:text-art-yellow max-md:gap-0 max-md:[&_h1]:text-[clamp(38px,9.6vw,64px)] max-md:[&_h1]:leading-[1.08] max-[359px]:[&_h1]:text-[36px]">
        <h1 id="landing-title">
          {tLanding('heroTitle1')}
          <br />
          {tLanding('heroTitle2')}
          <span>{tLanding('heroTitleHighlight')}</span>
        </h1>
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
          <Button asChild size="lg">
            <Link href="/signup">
              {tLanding('buildVocabulary')} <ArrowUpRight />
            </Link>
          </Button>
          <a className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]" href="#learning-map">
            {tLanding('tryWordBelow')} <ArrowDownIcon />
          </a>
        </div>
      </div>
    </section>
  )
}
