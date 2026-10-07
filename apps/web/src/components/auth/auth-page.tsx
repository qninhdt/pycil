'use client'

import { PycilBrand } from '@/components/application/brand'
import { ThemeButton } from '@/components/application/app-shell'
import { authConfigured } from '@/components/application/providers'
import { AuthForm } from './auth-form'
import { ConnectedAuthForm } from './clerk-form'
import type { AuthMode } from '@/lib/auth-flow'

export function AuthPage({ mode }: { mode: AuthMode }) {
  const signup = mode === 'signup'
  return <div className={`grid grid-cols-1 md:grid-cols-[minmax(0,1.38fr)_minmax(440px,1fr)] max-xl:md:grid-cols-[minmax(0,1fr)_minmax(410px,1fr)] min-h-svh max-md:flex max-md:flex-col${signup ? ' signup' : ''}`}>
    <a className="skip-link" href="#auth-form">Skip to form</a>
    <section className="relative overflow-hidden border-r border-foreground flex flex-col min-h-[860px] 2xl:min-h-[960px] max-md:min-h-[208px] max-md:h-[208px] max-md:border-r-0 max-md:border-b max-md:border-foreground max-md:shrink-0" aria-label="Pycil introduction">
      <svg className="absolute inset-0 w-full h-full max-md:w-full max-md:h-[380px] max-md:-translate-y-[90px]" viewBox="0 0 720 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <circle cx={signup ? '610' : '470'} cy={signup ? '120' : '190'} r={signup ? '200' : '143'} fill="var(--art-red)" />
        <rect x="0" y="690" width="204" height="210" fill="var(--art-blue)" />
        <path d="M720 355V900H230Z" fill="var(--art-yellow)" />
        <path d="M54 0v900M470 0v900M0 207h720M0 810h720M720 649a250 250 0 0 0-250 251" fill="none" stroke="var(--art-ink)" strokeWidth="1" />
      </svg>
      <div className="relative px-12 py-11 [&_svg]:w-44 [&_svg]:h-auto [&_p]:text-[11px] [&_p]:leading-[1.85] [&_p]:tracking-[.13em] [&_p]:mt-6 max-xl:px-8 max-xl:py-9 max-md:p-6 max-md:[&_svg]:w-[124px] max-md:[&_p]:hidden"><PycilBrand /><p>Words. Meanings.<br />Your own pace.</p></div>
      <div className="relative text-[clamp(68px,7.6vw,112px)] font-extrabold leading-[.98] tracking-[-.04em] mt-20 pl-12 pr-7 [&_>_span]:block [&_b]:text-art-red 2xl:text-[128px] max-xl:text-[clamp(62px,7.2vw,86px)] max-xl:pl-8 max-md:text-[32px] max-md:leading-[1.04] max-md:mt-0 max-md:pl-6 max-md:pr-4 max-md:[&_>_span]:inline max-md:max-w-[220px] max-md:text-balance" aria-hidden="true">{signup ? <><span>start </span><span>your </span><span>journey<b>.</b></span></> : <><span>build </span><span>your </span><span>language<b>.</b></span></>}</div>
      <p className="relative text-[11px] leading-[1.9] tracking-[.12em] mt-auto mr-0 mb-[100px] ml-[245px] pt-16 max-xl:ml-8 max-xl:px-4 max-xl:py-6 max-xl:mb-12 max-xl:bg-background max-xl:self-start max-md:hidden">A little practice.<br />A new perspective.</p>
    </section>
    <main className="min-w-0 flex flex-col py-6 px-[clamp(32px,4vw,64px)] pb-8 max-xl:px-8 max-md:pt-4 max-md:px-6 max-md:pb-8 max-[380px]:px-5" id="auth-form" tabIndex={-1}>
      <div className="flex items-center justify-between gap-3 mb-14 [&_>_span]:text-[11px] [&_>_span]:text-muted-foreground max-md:mb-5.5"><span>Learn at your own pace.</span><ThemeButton /></div>
      <div className="w-full max-w-[440px] mx-auto pt-4 pb-12 max-md:pt-0 max-md:pb-8">
        {authConfigured ? <ConnectedAuthForm key={mode} mode={mode} /> : <AuthForm key={mode} mode={mode} />}
      </div>
      <p className="text-[11px] text-muted-foreground text-center leading-[1.8]">Your progress stays personal.<br />Only the material you publish is public.</p>
    </main>
  </div>
}
