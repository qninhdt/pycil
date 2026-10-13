import { getRequestConfig } from 'next-intl/server'
import { cookies, headers } from 'next/headers'
import { defaultLocale, type Locale, locales } from '@/lib/i18n'

export default getRequestConfig(async () => {
  const cookieStore = await cookies()
  const headerStore = await headers()

  const cookieLocale = cookieStore.get('NEXT_LOCALE')?.value as Locale | undefined
  const headerLang = headerStore.get('accept-language')?.split(',')[0]?.split('-')[0] as Locale | undefined

  const locale: Locale =
    cookieLocale && locales.includes(cookieLocale)
      ? cookieLocale
      : headerLang && locales.includes(headerLang)
        ? headerLang
        : defaultLocale

  const messages =
    locale === 'vi'
      ? (await import('@/messages/vi.json')).default
      : (await import('@/messages/en.json')).default

  return {
    locale,
    messages,
  }
})
