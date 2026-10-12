import { getRequestConfig } from 'next-intl/server'
import { cookies } from 'next/headers'
import { defaultLocale, messages, type Locale } from '@/lib/i18n'

export default getRequestConfig(async () => {
  const cookieStore = await cookies()
  const rawLocale = cookieStore.get('NEXT_LOCALE')?.value
  const locale: Locale = rawLocale === 'vi' ? 'vi' : defaultLocale

  return {
    locale,
    messages: messages[locale],
  }
})
