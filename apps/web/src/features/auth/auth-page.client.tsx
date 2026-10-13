'use client'

import { PycilBrand } from '@/components/shell/brand'
import { authConfigured } from '@/lib/auth/config'
import { AuthForm } from './auth-form.client'
import { ConnectedAuthForm } from './clerk-form.client'
import type { AuthMode } from '@/features/auth/flow'
import { useTranslations } from 'next-intl'

export function AuthPage({ mode }: { mode: AuthMode }) {
  const signup = mode === 'signup'
  const t = useTranslations('auth')

  return <div className={`relative h-svh max-h-svh w-full overflow-hidden bg-background text-foreground grid grid-cols-1 md:grid-cols-[minmax(0,1.38fr)_minmax(420px,1fr)] max-xl:md:grid-cols-[minmax(0,1fr)_minmax(400px,1fr)]${signup ? ' signup' : ''}`}>
    <a className="skip-link" href="#auth-form">{t('skipToForm')}</a>

    {/* Artwork section: On mobile it acts as the full-screen background; slogans are hidden */}
    <section className="max-md:absolute max-md:inset-0 max-md:z-0 md:relative md:flex md:flex-col md:h-full md:border-r md:border-foreground md:overflow-hidden select-none pointer-events-none md:pointer-events-auto" aria-label={t('pycilIntroAria')}>
      <svg className="absolute inset-0 size-full pointer-events-none" viewBox="0 0 720 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <circle cx={signup ? '610' : '470'} cy={signup ? '120' : '190'} r={signup ? '200' : '143'} fill="var(--art-red)" />
        <rect x="0" y="690" width="204" height="210" fill="var(--art-blue)" />
        <path d="M720 355V900H230Z" fill="var(--art-yellow)" />
        <path d="M54 0v900M470 0v900M0 207h720M0 810h720M720 649a250 250 0 0 0-250 251" fill="none" stroke="var(--art-ink)" strokeWidth="1" />
      </svg>
      <div className="hidden md:block relative text-[clamp(48px,6vw,96px)] font-extrabold leading-[.98] tracking-[-.04em] my-auto pl-10 pr-6 [&_>_span]:block [&_b]:text-art-red 2xl:text-[112px] shrink-0" aria-hidden="true">
        {signup ? <><span>start </span><span>your </span><span>journey<b>.</b></span></> : <><span>build </span><span>your </span><span>language<b>.</b></span></>}
      </div>
      <p className="hidden md:block relative text-lg lg:text-xl font-bold leading-tight tracking-tight text-foreground mt-auto mr-0 mb-10 ml-10 lg:ml-16 max-xl:bg-background/90 max-xl:self-start shrink-0">
        {t('sloganLine1')}<br />
        <span className="text-muted-foreground font-semibold">{t('sloganLine2')}</span>
      </p>
    </section>

    {/* Form section: Centered card on mobile; right column on desktop */}
    <main className="relative z-10 min-w-0 flex flex-col items-center h-full overflow-y-auto px-4 py-12 md:py-8 md:justify-center md:px-[clamp(24px,3vw,52px)]" id="auth-form" tabIndex={-1}>
      <div className="w-full max-w-[390px] mx-auto my-auto border border-foreground bg-background p-6 sm:p-8 shadow-[4px_4px_0_var(--foreground)] md:border-0 md:bg-transparent md:p-0 md:shadow-none">
        <div className="relative z-20 flex max-md:justify-center max-md:mb-6 md:fixed md:top-8 md:left-10 md:mb-0">
          <PycilBrand />
        </div>
        {authConfigured ? <ConnectedAuthForm key={mode} mode={mode} /> : <AuthForm key={mode} mode={mode} />}
      </div>
    </main>
  </div>
}
