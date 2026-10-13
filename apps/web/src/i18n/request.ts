import { getRequestConfig } from 'next-intl/server'
import { cookies, headers } from 'next/headers'
import { resolveLocale } from '@/lib/preferences/locale'

export default getRequestConfig(async () => {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()])
  const locale = resolveLocale(cookieStore.get('NEXT_LOCALE')?.value, headerStore.get('accept-language'))

  const messages =
    locale === 'vi'
      ? (await import('@/messages/vi.json')).default
      : (await import('@/messages/en.json')).default

  return {
    locale,
    messages,
  }
})
