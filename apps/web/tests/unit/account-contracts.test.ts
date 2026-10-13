import { expect,test } from 'vitest'
import { parseAccountProfile, parsePublicProfile, parseUsageAllowance } from '../../src/lib/api/account'
import { ApiError } from '../../src/lib/api/error'
import database from '../../src/lib/api/services/mock/database.json' with { type: 'json' }

test('account contracts require a native plan, learning policy and explicit approval preference', () => {
  expect(parseAccountProfile(database.account)).toEqual(database.account)
  for (const patch of [{ plan: 'invented' }, { settings: null }, { learning_options: {} }, { settings: { ...database.account.settings, assistant: {} } }]) {
    expect(() => parseAccountProfile({ ...database.account, ...patch })).toThrow(ApiError)
  }
})

test('public profile strips private account data and supports bio without a handle', () => {
  const profile = parsePublicProfile({ ...database.account, handle: null, bio: 'Hello' })
  expect(profile).toEqual({ id: database.account.id, published_node_id: database.account.published_node_id, joined_at: database.account.joined_at, display_name: database.account.display_name, handle: null, bio: 'Hello' })
  expect(profile).not.toHaveProperty('settings')
  expect(profile).not.toHaveProperty('personal_node_id')
  expect(() => parsePublicProfile({ ...database.account, joined_at: 'invalid' })).toThrow(ApiError)
})

test('allowance uses backend units including overspend and rejects inconsistent data', () => {
  const allowance = { period_start: '2026-10-01T00:00:00Z', period_end: '2026-11-01T00:00:00Z', allowance_units: 100, used_units: 120, remaining_units: 0 }
  expect(parseUsageAllowance(allowance)).toEqual(allowance)
  expect(() => parseUsageAllowance({ ...allowance, remaining_units: 1 })).toThrow()
  expect(() => parseUsageAllowance({ ...allowance, used_units: -1 })).toThrow()
  expect(() => parseUsageAllowance({ ...allowance, period_end: allowance.period_start })).toThrow()
})

test('account parsing rejects partial policy, missing roots and malformed saved preferences before rendering', () => {
  const account = database.account
  for (const patch of [
    { personal_node_id: undefined }, { library_node_id: 42 }, { joined_at: 'invalid' },
    { settings: { ...account.settings, timezone: 'Mars/Olympus' } },
    { settings: { ...account.settings, locale: undefined } },
    { settings: { ...account.settings, learning: { ...account.settings.learning, formats: ['invented'] } } },
    { learning_options: { ...account.learning_options, limits: { min_questions_per_sense: 7, max_questions_per_sense: 1, max_questions_per_prepare: 100 } } },
    { learning_options: { ...account.learning_options, pairs: [{ question_type: 'cloze_to_word', format: 'invented', level: 1 }] } },
    { effective_learning: {} },
  ]) expect(() => parseAccountProfile({ ...account, ...patch })).toThrow(ApiError)
})
