import { expect, test } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { NextIntlClientProvider } from 'next-intl'
import { GradeDetails } from '../../src/features/study/grade-details.client'
import en from '../../src/messages/en.json'
import vi from '../../src/messages/vi.json'

test('approximate meaning is distinct from exact and current form diagnostics are localized', () => {
  const grade = { used: true, meaning: 'approximate', form: 'form_error', construction: null, collocation: null, appropriacy: null } as const
  const english = renderToStaticMarkup(<NextIntlClientProvider locale="en" messages={en}><GradeDetails grade={grade} /></NextIntlClientProvider>)
  const vietnamese = renderToStaticMarkup(<NextIntlClientProvider locale="vi" messages={vi}><GradeDetails grade={grade} /></NextIntlClientProvider>)
  expect(english).toContain(en.learning.approximate)
  expect(english).not.toContain('>Exact<')
  expect(vietnamese).toContain(vi.learning.approximate)
  expect(vietnamese).toContain(vi.learning.formIssue)
  expect(vietnamese).not.toContain('form error')
})
