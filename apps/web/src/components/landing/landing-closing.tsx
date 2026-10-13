import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { MarkPaths } from '@/components/shell/brand'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'

export async function LandingClosing() {
  const tLanding = await getTranslations('landing')

  return (
    <section
      className="relative flex items-center justify-between gap-10 overflow-hidden border-y border-[var(--palette-ink)] bg-art-yellow px-[8%] py-16 text-on-yellow [&_h2]:text-[clamp(56px,5.5vw,80px)] [&_h2]:font-extrabold [&_h2]:leading-[1.05] [&_h2]:tracking-[-.04em] [&_p]:mt-[22px] [&_p]:mb-[30px] [&_p]:text-sm [&_p]:leading-[1.75] [&_[data-slot=button]]:min-h-13 [&_[data-slot=button]]:bg-[var(--palette-ink)] [&_[data-slot=button]]:px-6 [&_[data-slot=button]]:text-sm [&_[data-slot=button]]:text-[var(--palette-canvas)] [&_[data-slot=button]:hover]:bg-[var(--palette-ink-soft)] [&_a:focus-visible]:outline-[var(--palette-ink)] max-md:gap-0 max-md:px-[6%] max-md:py-[42px] max-md:[&_h2]:text-[55px] max-md:[&_p]:max-w-[25ch]"
      aria-labelledby="closing-title"
    >
      <div>
        <h2 id="closing-title" className="whitespace-pre-line">{tLanding('closingTitle')}</h2>
        <p>{tLanding('closingDesc')}</p>
        <Button asChild size="lg">
          <Link href="/signup">
            {tLanding('createYourAccount')} <ArrowUpRight />
          </Link>
        </Button>
      </div>
      <svg
        className="mr-[6%] h-[260px] w-[220px] shrink-0 [--art-yellow:var(--palette-canvas)] max-md:absolute max-md:top-[35px] max-md:-right-[22px] max-md:mr-0 max-md:h-[110px] max-md:w-[90px]"
        viewBox="0 0 312 362"
        aria-hidden="true"
      >
        <MarkPaths />
      </svg>
    </section>
  )
}
