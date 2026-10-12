import { expect,test } from 'vitest'

import { getNextTimeOfDayChange,getTimeOfDay } from '../../src/lib/time-of-day'

test('day periods and their next boundaries use local calendar time', () => {
  for (const [hour, minute, period] of [[0, 0, 'night'], [4, 59, 'night'], [5, 0, 'morning'], [11, 59, 'morning'], [12, 0, 'afternoon'], [17, 59, 'afternoon'], [18, 0, 'night'], [23, 59, 'night']] as const) {
    const date = new Date(2026, 9, 7, hour, minute)
    expect(getTimeOfDay(date)).toBe(period)
    const next = getNextTimeOfDayChange(date)
    expect(next.getTime()).toBeGreaterThan(date.getTime())
    expect([5, 12, 18]).toContain(next.getHours())
    expect(next.getMinutes()).toBe(0)
    expect(getTimeOfDay(next)).not.toBe(period)
  }
  expect(getNextTimeOfDayChange(new Date(2026, 9, 7, 18))).toEqual(new Date(2026, 9, 8, 5))
})
