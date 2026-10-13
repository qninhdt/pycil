'use client'

import React, { createContext, useContext, useEffect, useState } from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { defaultLocale, setStoredLocale, getStoredLocale, type Locale } from '@/lib/i18n'
import en from '@/messages/en.json'
import vi from '@/messages/vi.json'

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
}

const I18nContext = createContext<I18nContextValue>({
  locale: defaultLocale,
  setLocale: () => {},
})

export const useI18n = () => useContext(I18nContext)

export function I18nProvider({
  children,
  initialLocale = defaultLocale,
}: {
  children: React.ReactNode
  initialLocale?: Locale
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)

  useEffect(() => {
    const stored = getStoredLocale()
    setLocaleState((curr) => (curr !== stored ? stored : curr))
    document.documentElement.lang = stored
  }, [])

  const handleSetLocale = (next: Locale) => {
    setLocaleState(next)
    setStoredLocale(next)
  }

  return (
    <I18nContext.Provider value={{ locale, setLocale: handleSetLocale }}>
      <NextIntlClientProvider
        locale={locale}
        messages={locale === 'vi' ? vi : en}
        onError={() => {}}
        getMessageFallback={({ key }) => key}
      >
        {children}
      </NextIntlClientProvider>
    </I18nContext.Provider>
  )
}
