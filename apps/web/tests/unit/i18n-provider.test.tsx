import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { useTranslations } from 'next-intl'
import { expect, test } from 'vitest'
import { I18nProvider } from '../../src/components/application/i18n-provider'

function TimeZoneLabel() {
  const t = useTranslations('account')
  return <label>{t('timeZone')}</label>
}

test.each([['en', 'Time zone'], ['vi', 'Múi giờ']] as const)(
  'locale %s renders its own messages', (locale, label) => {
    expect(renderToStaticMarkup(<I18nProvider initialLocale={locale}><TimeZoneLabel /></I18nProvider>))
      .toBe(`<label>${label}</label>`)
  },
)
