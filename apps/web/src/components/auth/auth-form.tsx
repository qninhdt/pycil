'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { ArrowLeft, ArrowRight, Eye, EyeOff, LoaderCircle } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { authConfigured } from '@/components/application/providers'
import { authErrorMessage, type AuthDriver, type AuthFields, type AuthMode, type AuthStep } from '@/lib/auth-flow'

export function AuthForm({ mode, driver, unavailable = false }: { mode: AuthMode; driver?: AuthDriver; unavailable?: boolean }) {
  const signup = mode === 'signup'
  const [step, setStep] = useState<AuthStep>('credentials')
  const [shown, setShown] = useState<Record<string, boolean>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [continuation, setContinuation] = useState(false)
  const [busy, setBusy] = useState(false)
  const { register, handleSubmit, getValues, resetField, formState: { errors } } = useForm<AuthFields>({ shouldUnregister: true })
  const verifying = step.startsWith('verify-') || step === 'reset-code'
  const passwordRequired = step === 'new-password' || (step === 'credentials' && mode !== 'reset')
  const title = step === 'new-password' ? 'A fresh start.' : verifying ? 'Check your inbox.'
    : signup ? 'Create your account.' : mode === 'reset' ? 'Forgot your password?' : 'Welcome back.'
  const heading = step === 'verify-totp' ? 'Verify your sign-in.' : title
  const description = verifying ? step === 'verify-totp' ? 'Enter the code from your authenticator app.' : 'Enter the verification code sent to your email.'
    : step === 'new-password' ? 'Choose a new password for your account.'
      : signup ? 'Make room for your next new meaning.' : mode === 'reset' ? 'We’ll send you a code to reset it.' : 'Pick up where you left off.'
  const action = verifying ? 'Verify and continue' : step === 'new-password' ? 'Reset password' : signup ? 'Create account' : mode === 'reset' ? 'Send reset code' : 'Sign in'
  const loading = authConfigured && !driver?.ready && !unavailable
  const apply = (result: { step?: AuthStep; message?: string; continuation?: boolean }) => {
    if (result.step) { setStep(result.step); resetField('password'); resetField('confirm'); resetField('code') }
    if (result.message) setNotice(result.message)
    setContinuation(Boolean(result.continuation))
  }
  const submit = handleSubmit(async fields => {
    setError(''); setNotice(''); setContinuation(false)
    if (!driver?.ready) { setError(authConfigured ? 'The sign-in service is unavailable. Please reload and try again.' : 'Sign-in is not configured yet. Add the Clerk keys to run authentication.'); return }
    setBusy(true)
    try { apply(await driver.submit(fields, step)) } catch (cause) { setError(authErrorMessage(cause)) } finally { setBusy(false) }
  })
  const fieldError = (name: keyof AuthFields) => errors[name] ? <p id={`${name}-error`} className="text-destructive text-xs leading-relaxed">{errors[name]?.message}</p> : null
  const passwordField = (name: 'password' | 'confirm', label: string) => <div className="flex flex-col gap-2.5">
    <div className="flex justify-between items-center gap-3 [&_a]:text-xs [&_a]:underline [&_a]:underline-offset-4"><label htmlFor={name}>{label}</label>{name === 'password' && mode === 'login' && step === 'credentials' && <Link href="/forgot-password">Forgot password?</Link>}</div>
    <div className="relative [&_[data-slot=input]]:pr-[54px] [&_button]:absolute [&_button]:right-1.5 [&_button]:top-1.5"><Input id={name} type={shown[name] ? 'text' : 'password'} autoComplete={signup || mode === 'reset' ? 'new-password' : 'current-password'}
      placeholder={name === 'confirm' ? 'Re-enter your password' : 'Enter your password'} aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? `${name}-error` : undefined}
      {...register(name, { required: 'Enter your password.',
        ...(signup || mode === 'reset' ? { minLength: { value: 8, message: 'Use at least 8 characters.' } } : {}),
        ...(name === 'confirm' ? { validate: (value: string) => value === getValues('password') || 'The passwords do not match.' } : {}),
      })} />
      <Button type="button" variant="ghost" size="icon" onClick={() => setShown(value => ({ ...value, [name]: !value[name] }))}
        aria-label={`${shown[name] ? 'Hide' : 'Show'} ${name === 'confirm' ? 'confirm password' : 'password'}`} aria-pressed={Boolean(shown[name])}>{shown[name] ? <EyeOff /> : <Eye />}</Button>
    </div>{fieldError(name)}
  </div>
  return <>
    <header className="mb-11 [&_h1]:text-[clamp(36px,3.5vw,52px)] [&_h1]:font-extrabold [&_h1]:tracking-[-0.04em] [&_h1]:leading-[1.08] [&_h1]:text-balance [&_h1_>_span]:text-art-red [&_p]:text-sm [&_p]:text-muted-foreground [&_p]:mt-4 [&_p]:leading-relaxed max-md:mb-8 max-md:[&_h1]:text-4xl max-md:[&_p]:text-[13px] max-md:[&_p]:mt-3 max-[380px]:[&_h1]:text-[32px]"><h1>{heading.replace(/[.]$/, '')}<span>{heading.endsWith('.') ? '.' : ''}</span></h1><p>{description}</p></header>
    <form className="authentication-form [&_fieldset]:flex [&_fieldset]:flex-col [&_fieldset]:gap-6 [&_fieldset]:min-w-0 [&_label]:text-[13px] [&_label]:font-[650] [&_[data-slot=input]]:h-[52px] [&_[data-slot=input]]:px-4 [&_[data-slot=input]]:py-3 [&_[data-slot=input]]:bg-background max-md:[&_fieldset]:gap-[22px] max-md:[&_[data-slot=input]]:text-base" onSubmit={submit} noValidate aria-busy={busy}>
      <fieldset disabled={busy}>
        {step === 'credentials' && <div className="flex flex-col gap-2.5"><label htmlFor="email">Email</label><Input id="email" type="email" autoComplete="email" inputMode="email" placeholder="you@example.com"
          aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? 'email-error' : undefined}
          {...register('email', { required: 'Enter your email address.', pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: 'Enter a valid email address.' } })} />{fieldError('email')}</div>}
        {verifying && <div className="flex flex-col gap-2.5"><label htmlFor="code">Verification code</label><Input id="code" type="text" inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code"
          aria-invalid={Boolean(errors.code)} aria-describedby={errors.code ? 'code-error' : undefined}
          {...register('code', { required: 'Enter the verification code.', pattern: { value: /^\d{6}$/, message: 'Enter the 6-digit verification code.' } })} />{fieldError('code')}</div>}
        {passwordRequired && passwordField('password', step === 'new-password' ? 'New password' : 'Password')}
        {passwordRequired && (signup || step === 'new-password') && passwordField('confirm', 'Confirm password')}
        {error && <p className="text-destructive text-xs leading-relaxed py-3 border-y border-border" role="alert">{error}</p>}
        {notice && <p className="py-3 border-y border-border text-[13px] leading-relaxed" role="status">{notice}</p>}
        {continuation && <Link href={signup ? '/auth/signup' : '/auth/continue'} className="inline-flex items-center gap-2 min-h-[44px] underline underline-offset-4 [&_svg]:size-[15px]">Continue securely <ArrowRight aria-hidden="true" /></Link>}
        <Button type="submit" size="lg" className="mt-1 w-full" disabled={loading}>{busy || loading ? <><LoaderCircle className="animate-spin" />{loading ? 'Connecting…' : 'Please wait…'}</> : <>{action}<ArrowRight data-icon="inline-end" aria-hidden="true" /></>}</Button>
      </fieldset>
      {verifying && step !== 'verify-totp' && <Button type="button" variant="link" disabled={busy || !driver?.ready} onClick={async () => {
        setBusy(true); setError(''); setNotice('')
        try { await driver?.resend(step); setNotice('A new code has been sent. Check your inbox.') } catch (cause) { setError(authErrorMessage(cause)) } finally { setBusy(false) }
      }}>Send a new code</Button>}
      <div id="clerk-captcha" />
    </form>
    {step === 'credentials' && mode !== 'reset' && <>
      <div className="flex items-center gap-5 text-muted-foreground text-[11px] my-7 [&_span]:h-px [&_span]:bg-border [&_span]:flex-1"><span />or<span /></div>
      <Button className="w-full justify-between" variant="outline" size="lg" disabled={busy || loading} onClick={async () => {
        setError(''); setNotice('')
        if (!driver?.ready) { setError(authConfigured ? 'Google sign-in is unavailable. Please reload and retry.' : 'Google sign-in needs the Clerk configuration.'); return }
        setBusy(true)
        try { apply(await driver.google()) } catch (cause) { setError(authErrorMessage(cause)) } finally { setBusy(false) }
      }}>Continue with Google<ArrowRight aria-hidden="true" /></Button>
    </>}
    <p className="flex justify-center items-center flex-wrap gap-1.5 mt-8 text-xs leading-relaxed [&_a]:inline-flex [&_a]:items-center [&_a]:gap-2 [&_a]:min-h-[44px] [&_a]:underline [&_a]:underline-offset-4 [&_a_svg]:size-[15px] max-md:mt-6">{mode === 'reset' || verifying || step === 'new-password' ? <Link href={signup ? '/signup' : '/login'}><ArrowLeft aria-hidden="true" />Back to {signup ? 'sign up' : 'sign in'}</Link>
      : <>{signup ? 'Already have an account?' : 'New to Pycil?'} <Link href={signup ? '/login' : '/signup'}>{signup ? 'Sign in' : 'Create an account'}<ArrowRight aria-hidden="true" /></Link></>}</p>
    {(!authConfigured || unavailable) && <p className="text-muted-foreground text-[11px] leading-[1.65] mt-5 border-t border-border pt-4 [&_button]:underline [&_button]:underline-offset-[3px]" role="status">{authConfigured ? <>Unable to reach the sign-in service. <button onClick={() => window.location.reload()}>Reload</button> to retry.</>
      : 'Authentication needs Clerk configuration. You can explore the app foundation without signing in.'}</p>}
  </>
}
