export type AuthMode = 'login' | 'signup' | 'reset'
export type AuthStep = 'credentials' | 'verify-email' | 'verify-mfa' | 'verify-totp' | 'reset-code' | 'new-password'
export type AuthFields = { email: string; password: string; confirm: string; code: string }
export type AuthResult = { step?: AuthStep; message?: string; continuation?: boolean }
export type AuthDriver = {
  ready: boolean
  submit: (fields: AuthFields, step: AuthStep) => Promise<AuthResult>
  google: () => Promise<AuthResult>
  resend: (step: AuthStep) => Promise<void>
}

export function safeReturnTo(value: string | null | undefined) {
  // Only the application subtree is a valid post-auth destination.
  if (!value || !/^\/app(?:\/|\?|$)/.test(value) || /[\\\r\n]/.test(value)) return '/app'
  return value
}

export function authErrorMessage(error: unknown) {
  const codes: Record<string, string> = {
    form_password_incorrect: 'The email or password is incorrect. Please try again.',
    form_identifier_not_found: 'The email or password is incorrect. Please try again.',
    form_identifier_exists: 'An account already uses this email. Try signing in instead.',
    form_code_incorrect: 'That code is not correct. Check it and try again.',
    verification_expired: 'This code has expired. Request a new code.',
    too_many_requests: 'Too many attempts. Wait a moment before trying again.',
    form_password_pwned: 'This password has appeared in a data breach. Choose a different password.',
    form_password_length_too_short: 'Choose a longer password.',
    captcha_invalid: 'The security check did not complete. Please try again.',
  }
  if (error && typeof error === 'object') {
    const value = error as { code?: string; errors?: { code?: string; longMessage?: string; message?: string }[] }
    const item = value.errors?.[0]
    const code = item?.code || value.code
    if (code && codes[code]) return codes[code]
    if (item?.longMessage || item?.message) return item.longMessage || item.message || ''
  }
  return 'Authentication did not complete. Check your connection and try again.'
}
