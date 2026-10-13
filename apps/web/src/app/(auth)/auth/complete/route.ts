import { auth } from '@clerk/nextjs/server'
import { cookies } from 'next/headers'
import { NextResponse, type NextRequest } from 'next/server'
import { loadServerAccount } from '@/lib/auth/account'
import { safeReturnTo } from '@/features/auth/flow'
import { resolveLocale } from '@/lib/preferences/locale'

export async function GET(request: NextRequest) {
  await auth.protect()
  const account = await loadServerAccount()
  if (!account) throw new Error('The signed-in account could not be loaded.')
  const locale = resolveLocale(account.settings.locale, null)
  const jar = await cookies()
  jar.set('NEXT_LOCALE', locale, { path: '/', maxAge: 31536000, sameSite: 'lax', secure: request.nextUrl.protocol === 'https:' })
  return NextResponse.redirect(new URL(safeReturnTo(request.nextUrl.searchParams.get('returnTo')), request.url))
}
