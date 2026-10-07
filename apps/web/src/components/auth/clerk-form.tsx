'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useClerk, useSignIn, useSignUp } from '@clerk/nextjs'
import { AuthForm } from './auth-form'
import { safeReturnTo, type AuthDriver, type AuthMode, type AuthResult } from '@/lib/auth-flow'

export function ConnectedAuthForm({ mode }: { mode: AuthMode }) {
  const clerk = useClerk()
  const { signIn } = useSignIn()
  const { signUp } = useSignUp()
  const router = useRouter()
  const search = useSearchParams()
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    if (clerk.loaded) return
    const timer = setTimeout(() => setUnavailable(true), 12000)
    return () => clearTimeout(timer)
  }, [clerk.loaded])
  const destination = safeReturnTo(search.get('returnTo'))
  const finish = async (signup: boolean): Promise<AuthResult> => {
    let task = false
    const resource = signup ? signUp : signIn
    const result = await resource.finalize({ navigate: ({ session }) => {
      if (session?.currentTask) { task = true; router.replace('/auth/continue') }
      else router.replace(destination)
    } })
    if (result.error) throw result.error
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
    ready: clerk.loaded,
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
      const result = await (mode === 'signup' ? signUp : signIn).sso({ strategy: 'oauth_google', redirectCallbackUrl: '/sso-callback', redirectUrl: destination })
      if (result.error) throw result.error
      return {}
    },
    resend: async step => {
      const result = step === 'reset-code' ? await signIn.resetPasswordEmailCode.sendCode()
        : step === 'verify-email' ? await signUp.verifications.sendEmailCode() : await signIn.mfa.sendEmailCode()
      if (result.error) throw result.error
    },
  }
  return <AuthForm mode={mode} driver={driver} unavailable={unavailable && !clerk.loaded} />
}
