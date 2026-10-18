// @vitest-environment happy-dom
import { afterEach, expect, test } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { GradeDetails } from '../../src/features/study/grade-details.client'
import en from '../../src/messages/en.json'
import vi from '../../src/messages/vi.json'

afterEach(() => {
  cleanup()
})

test('approximate meaning is distinct from exact and current form diagnostics are localized using DOM assertions', () => {
  const grade = {
    used: true,
    meaning: 'approximate',
    form: 'form_error',
    construction: null,
    collocation: null,
    appropriacy: null,
  } as const

  // English render
  const { unmount } = render(
    <NextIntlClientProvider locale="en" messages={en} timeZone="UTC">
      <GradeDetails grade={grade} />
    </NextIntlClientProvider>,
  )

  const approxPill = screen.getByText(en.learning.approximate)
  expect(approxPill).toBeDefined()
  expect(screen.queryByText('Exact')).toBeNull()

  // Verify diagnostic details toggle works and expands dl
  const detailsButton = screen.getByRole('button', { name: en.learning.diagnosticDetails })
  expect(detailsButton.getAttribute('aria-expanded')).toBe('false')

  fireEvent.click(detailsButton)
  expect(detailsButton.getAttribute('aria-expanded')).toBe('true')
  expect(screen.getByText(en.learning.targetUsed)).toBeDefined()

  unmount()

  // Vietnamese render
  render(
    <NextIntlClientProvider locale="vi" messages={vi} timeZone="UTC">
      <GradeDetails grade={grade} />
    </NextIntlClientProvider>,
  )

  expect(screen.getByText(vi.learning.approximate)).toBeDefined()
  expect(screen.getByText(vi.learning.formIssue)).toBeDefined()
  expect(screen.queryByText('form error')).toBeNull()
})

test('returns null when grade is null', () => {
  const { container } = render(
    <NextIntlClientProvider locale="en" messages={en} timeZone="UTC">
      <GradeDetails grade={null} />
    </NextIntlClientProvider>,
  )
  expect(container.firstChild).toBeNull()
})
