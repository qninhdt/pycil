import { getTranslations } from 'next-intl/server'
import { LandingHeader } from './landing-header'
import { LandingHero } from './landing-hero'
import { LearningMap } from './learning-map.client'
import { LandingLibrary } from './landing-library'
import { LandingPrinciples } from './landing-principles'
import { LandingClosing } from './landing-closing'
import { LandingFooter } from './landing-footer'

export async function LandingPage() {
  const tNav = await getTranslations('nav')

  return (
    <div className="mx-auto max-w-[1600px] bg-background text-foreground [&_a:focus-visible]:outline-2 [&_a:focus-visible]:outline-offset-4 [&_a:focus-visible]:outline-ring [&_button:focus-visible]:outline-2 [&_button:focus-visible]:outline-offset-4 [&_button:focus-visible]:outline-ring">
      <a className="skip-link" href="#landing-content">
        {tNav('skipToContent')}
      </a>
      <LandingHeader />
      <main id="landing-content" tabIndex={-1}>
        <LandingHero />
        <LearningMap />
        <LandingLibrary />
        <LandingPrinciples />
        <LandingClosing />
      </main>
      <LandingFooter />
    </div>
  )
}
