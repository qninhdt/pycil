import { webConfig } from '@/config'
export const locales = ['en', 'vi'] as const
export type Locale = (typeof locales)[number]
export const defaultLocale: Locale = 'en'

export const localeNames: Record<Locale, string> = {
  en: 'English',
  vi: 'Tiếng Việt',
}

export function resolveLocale(cookie: string | undefined, acceptLanguage: string | null): Locale {
  if (cookie === 'en' || cookie === 'vi') return cookie
  const languages = (acceptLanguage ?? '').split(',').map(item => {
    const [tag, ...parameters] = item.trim().toLowerCase().split(';')
    const quality = parameters.find(value => value.trim().startsWith('q='))
    return { locale: tag.split('-')[0], quality: quality ? Number(quality.trim().slice(2)) : 1 }
  }).filter(item => item.quality > 0 && item.quality <= 1).sort((a, b) => b.quality - a.quality)
  return languages.find(item => item.locale === 'en' || item.locale === 'vi')?.locale as Locale ?? defaultLocale
}

export function setLocaleCookie(locale: Locale): void {
  document.cookie = `NEXT_LOCALE=${locale}; Path=/; Max-Age=${webConfig.preferences.localeCookieSeconds}; SameSite=Lax`
}

export type Messages = typeof import('@/messages/en.json')

declare module 'next-intl' {
  interface AppConfig {
    Messages: Messages
    Locale: Locale
  }
}
