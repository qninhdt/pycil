import { getTranslations } from 'next-intl/server'
import { PycilBrand } from '@/components/shell/brand'
import { LandingAccount } from './landing-account.client'

export async function LandingHeader() {
  const tLanding = await getTranslations('landing')
  const tNav = await getTranslations('nav')

  return (
    <header className="mx-[4%] flex min-h-24 items-center justify-between gap-6 border-b border-foreground max-md:mx-[6%] max-md:min-h-20 max-md:gap-3">
      <PycilBrand />
      <nav
        aria-label={tNav('mainNav')}
        className="flex items-center gap-8 text-[13px] font-semibold [&_>_a:not([data-slot]):hover]:underline [&_>_a]:underline-offset-4 max-[1100px]:gap-5 max-md:gap-4 max-md:[&_>_a:nth-child(-n+2)]:hidden max-md:[&_[data-slot=button]]:px-3 max-[359px]:[&_>_a:nth-child(3)]:hidden"
      >
        <a href="/#learning-map">{tLanding('howItWorks')}</a>
        <a href="/#library">{tLanding('yourLibrary')}</a>
        <LandingAccount />
      </nav>
    </header>
  )
}
