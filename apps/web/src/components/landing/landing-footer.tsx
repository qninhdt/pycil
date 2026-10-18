import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { PycilBrand } from '@/components/shell/brand'
import { ArrowRight } from '@/components/artwork/artwork'

export async function LandingFooter() {
  const tLanding = await getTranslations('landing')

  return (
    <footer className="flex min-h-[120px] items-center justify-between gap-6 px-[4%] py-6 [&_>_p]:text-xs [&_>_p]:text-muted-foreground max-md:flex-wrap max-md:gap-5 max-md:px-[6%] max-md:py-7 max-md:[&_>_p]:order-3 max-md:[&_>_p]:basis-full">
      <PycilBrand />
      <p>{tLanding('footerTagline')}</p>
      <nav aria-label="Legal" className="flex gap-5 text-xs underline-offset-4 [&_a:hover]:underline">
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/terms">Terms of Service</Link>
      </nav>
      <Link
        className="inline-flex min-h-11 items-center justify-between gap-3.5 text-[13px] font-bold underline-offset-4 hover:underline [&_svg]:size-[18px]"
        href="/app"
      >
        {tLanding('openApp')} <ArrowRight />
      </Link>
    </footer>
  )
}
