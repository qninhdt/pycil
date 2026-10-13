'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useClerk, useSession, useSignIn, useSignUp } from '@clerk/nextjs'
import { useTranslations } from 'next-intl'
import { AuthForm } from './auth-form.client'
import { safeReturnTo, type AuthDriver, type AuthMode, type AuthResult } from '@/features/auth/flow'

function ensureLocalhostClientUat(session: { lastActiveAt?: Date } | null | undefined) {
  if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || !window.location.hostname.includes('.'))) {
    const uat = session?.lastActiveAt
      ? Math.floor(new Date(session.lastActiveAt).getTime() / 1000)
      : Math.floor(Date.now() / 1000) - 5
    document.cookie = `__client_uat=${uat}; path=/; max-age=31536000; samesite=lax`
  }
}

export function ConnectedAuthForm({ mode }: { mode: AuthMode }) {
  const clerk = useClerk()
  const { isLoaded, session } = useSession()
  const t = useTranslations('auth')
  const { signIn } = useSignIn()
  const { signUp } = useSignUp()
  const router = useRouter()
  const search = useSearchParams()
  const [unavailable, setUnavailable] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (clerk.loaded && isLoaded) return
    const timer = setTimeout(() => setUnavailable(true), 12000)
    return () => clearTimeout(timer)
  }, [clerk.loaded, isLoaded])

  // Latch initial session presence once Clerk has finished loading
  const initialSessionRef = useRef<boolean | null>(null)
  if (isLoaded && initialSessionRef.current === null) {
    initialSessionRef.current = Boolean(session)
  }
  const isAlreadySignedIn = isLoaded && initialSessionRef.current === true && !submitting

  const destination = safeReturnTo(search.get('returnTo'))
  const redirectTo = isLoaded && session ? session.currentTask ? '/auth/continue' : destination : null

  // Auto-redirect only if the user visited /login while already authenticated
  useEffect(() => {
    if (isAlreadySignedIn && redirectTo) {
      ensureLocalhostClientUat(session)
      if (redirectTo === '/auth/continue') router.replace(redirectTo)
      else window.location.replace(`/auth/complete?returnTo=${encodeURIComponent(redirectTo)}`)
    }
  }, [isAlreadySignedIn, redirectTo, session, router])

  const finish = async (signup: boolean): Promise<AuthResult> => {
    setSubmitting(true)
    let task = false
    const resource = signup ? signUp : signIn
    const result = await resource.finalize({
      navigate: ({ session, decorateUrl }) => {
        ensureLocalhostClientUat(session)
        const target = session?.currentTask ? '/auth/continue' : `/auth/complete?returnTo=${encodeURIComponent(destination)}`
        const destinationUrl = decorateUrl ? decorateUrl(target) : target
        if (destinationUrl.startsWith('http')) {
          window.location.href = destinationUrl
        } else if (session?.currentTask) {
          task = true
          router.replace('/auth/continue')
        } else {
          window.location.replace(destinationUrl)
        }
      }
    })
    if (result.error) {
      setSubmitting(false)
      throw result.error
    }
    return task ? { message: 'Complete the additional account verification to continue.', continuation: true } : {}
  }
  const nextSignInStep = async (): Promise<AuthResult> => {
    if (signIn.status === 'complete') return finish(false)
    if (signIn.status === 'needs_new_password') return { step: 'new-password' }
    if (signIn.status === 'needs_second_factor' || signIn.status === 'needs_client_trust') {
      const factors = signIn.supportedSecondFactors || []
      if (factors.some(factor => factor.strategy === 'totp')) return { step: 'verify-totp' }
      if (factors.some(factor => factor.strategy === 'email_code')) {
        const result = await signIn.mfa.sendEmailCode()
        if (result.error) throw result.error
        return { step: 'verify-mfa' }
      }
    }
    return { message: 'Your account requires an additional sign-in step. Continue securely to finish it.', continuation: true }
  }
  const nextSignUpStep = async (): Promise<AuthResult> => {
    if (signUp.status === 'complete') return finish(true)
    if (signUp.unverifiedFields.includes('email_address') && signUp.missingFields.length === 0) {
      const result = await signUp.verifications.sendEmailCode()
      if (result.error) throw result.error
      return { step: 'verify-email' }
    }
    return { message: 'Your account needs additional information. Continue securely to complete sign up.', continuation: true }
  }
  const driver: AuthDriver = {
    ready: clerk.loaded && isLoaded && !session,
    submit: async (fields, step) => {
      if (step === 'verify-email') {
        const result = await signUp.verifications.verifyEmailCode({ code: fields.code })
        if (result.error) throw result.error
        return signUp.status === 'complete' ? finish(true) : { message: 'Additional account information is required.', continuation: true }
      }
      if (step === 'verify-mfa' || step === 'verify-totp') {
        const result = step === 'verify-totp' ? await signIn.mfa.verifyTOTP({ code: fields.code }) : await signIn.mfa.verifyEmailCode({ code: fields.code })
        if (result.error) throw result.error
        return nextSignInStep()
      }
      if (step === 'reset-code') {
        const result = await signIn.resetPasswordEmailCode.verifyCode({ code: fields.code })
        if (result.error) throw result.error
        return { step: 'new-password' }
      }
      if (step === 'new-password') {
        const result = await signIn.resetPasswordEmailCode.submitPassword({ password: fields.password, signOutOfOtherSessions: true })
        if (result.error) throw result.error
        return nextSignInStep()
      }
      if (mode === 'reset') {
        const created = await signIn.create({ identifier: fields.email.trim() })
        if (created.error) throw created.error
        const result = await signIn.resetPasswordEmailCode.sendCode()
        if (result.error) throw result.error
        return { step: 'reset-code' }
      }
      const result = mode === 'signup'
        ? await signUp.password({ emailAddress: fields.email.trim(), password: fields.password })
        : await signIn.password({ emailAddress: fields.email.trim(), password: fields.password })
      if (result.error) throw result.error
      return mode === 'signup' ? nextSignUpStep() : nextSignInStep()
    },
    google: async () => {
      const result = await (mode === 'signup' ? signUp : signIn).sso({ strategy: 'oauth_google', redirectCallbackUrl: '/sso-callback', redirectUrl: `/auth/complete?returnTo=${encodeURIComponent(destination)}` })
      if (result.error) throw result.error
      return {}
    },
    resend: async step => {
      const result = step === 'reset-code' ? await signIn.resetPasswordEmailCode.sendCode()
        : step === 'verify-email' ? await signUp.verifications.sendEmailCode() : await signIn.mfa.sendEmailCode()
      if (result.error) throw result.error
    },
  }
  if ((!isLoaded && !unavailable) || (isAlreadySignedIn && redirectTo)) return <p role="status">{t('connecting')}</p>
  return <AuthForm mode={mode} driver={driver} unavailable={unavailable && (!clerk.loaded || !isLoaded)} />
}
