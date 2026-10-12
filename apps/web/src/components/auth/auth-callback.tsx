'use client'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AuthenticateWithRedirectCallback, SignIn, SignUp } from '@clerk/nextjs'
import { authConfigured } from '@/components/application/providers'

export function AuthCallback({ continuation = false, signupContinuation = false }: { continuation?: boolean; signupContinuation?: boolean }) {
  const t = useTranslations('auth')
  if (!authConfigured) return <div className="px-8 py-16 flex flex-col gap-5 max-w-[680px] mx-auto [&_h1]:text-[32px] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_a]:underline [&_a]:underline-offset-4"><h1>{t('authNotConfigured')}</h1><p>{t('addClerkConfig')}</p><Link href="/login">{t('backToSignIn')}</Link></div>
  return <div className="flex flex-col gap-6 justify-center items-center min-h-svh p-6">
    {signupContinuation ? <SignUp routing="path" path="/auth/signup" fallbackRedirectUrl="/app" signInUrl="/login" />
      : continuation ? <SignIn routing="path" path="/auth/continue" fallbackRedirectUrl="/app" signUpUrl="/signup" />
      : <><p role="status">{t('completingSecureSignIn')}</p><AuthenticateWithRedirectCallback signInUrl="/login" signUpUrl="/signup"
        signInFallbackRedirectUrl="/app" signUpFallbackRedirectUrl="/app" continueSignUpUrl="/auth/signup"
        secondFactorUrl="/auth/continue" firstFactorUrl="/auth/continue" resetPasswordUrl="/forgot-password" /></>}
    <div id="clerk-captcha" />
  </div>
}
