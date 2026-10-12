import en from '@/messages/en.json'
import vi from '@/messages/vi.json'

export const locales = ['en', 'vi'] as const
export type Locale = (typeof locales)[number]
export const defaultLocale: Locale = 'en'

export const localeNames: Record<Locale, string> = {
  en: 'English',
  vi: 'Tiếng Việt',
}

export const messages: Record<Locale, typeof en> = {
  en,
  vi,
}

export const localeStorageKey = 'pycil-locale'

export function getStoredLocale(): Locale {
  if (typeof window === 'undefined') return defaultLocale
  try {
    const item = localStorage.getItem(localeStorageKey)
    if (item === 'en' || item === 'vi') return item
  } catch {
    // Storage access is optional
  }
  return defaultLocale
}

export function setStoredLocale(locale: Locale): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(localeStorageKey, locale)
    document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; SameSite=Lax`
    document.documentElement.lang = locale
  } catch {
    // Storage access is optional
  }
}

declare module 'next-intl' {
  interface AppConfig {
    Messages: typeof en
    Locale: Locale
  }
}
