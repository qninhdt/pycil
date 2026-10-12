import { expect,test } from 'vitest'
import { ApiError,parseAccountProfile,parsePublicProfile,parseUsageAllowance } from '../../src/lib/api'
import database from '../../src/lib/services/mock/database.json' with { type: 'json' }

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
