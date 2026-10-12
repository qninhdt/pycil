import { expect,test } from 'vitest'

import { HomeApiError,parseActivity,parseLibrary,parseSchedule,parseSummary } from '../../src/lib/home-api'

const summary = { node_id: 'library-root', as_of: '2026-10-07T02:00:00Z', total: 142, new: 46, studied: 96, due: 12, not_due: 84, last_studied_at: '2026-10-06T02:00:00Z', reachable_decks: 4 }

test('Home contracts reject missing counts, inconsistent totals and incomplete reporting windows', () => {
  expect(parseSummary(summary)).toMatchObject({ total: 142, due: 12 })
  for (const value of [{ ...summary, due: null }, { ...summary, total: 999 }, { ...summary, due: -1 }]) expect(() => parseSummary(value)).toThrow(HomeApiError)
  const value = { as_of: summary.as_of, timezone: 'UTC', start_date: '2026-10-01', end_date: '2026-10-02', current_streak: 0, longest_streak: 0, applied_events: 0, practice_events: 0,
    days: [{ day: '2026-10-01', applied_events: 0, practice_events: 0 }] }
  expect(() => parseActivity(value)).toThrow(HomeApiError)
  expect(() => parseActivity({ ...value, days: [...value.days, { day: '2026-10-02', applied_events: 0, practice_events: 0 }] })).not.toThrow()
  expect(() => parseSchedule({ ...value, node_id: 'root', days: [] })).toThrow(HomeApiError)
  expect(() => parseLibrary({ nodes: [], next_cursor: null })).not.toThrow()
})
