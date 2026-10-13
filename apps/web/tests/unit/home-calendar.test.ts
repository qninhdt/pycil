import { expect,test } from 'vitest'

import { activityLevel,monthCells,reportingDay,shiftDay } from '../../src/features/home/calendar'

test('Home calendar respects reporting timezone, leap months and monotonic activity levels', () => {
  expect(reportingDay(new Date('2026-10-06T18:00:00Z'), 'Asia/Ho_Chi_Minh')).toBe('2026-10-07')
  expect(reportingDay(new Date('2026-10-06T18:00:00Z'), 'America/New_York')).toBe('2026-10-06')
  expect(shiftDay('2024-03-01', -1)).toBe('2024-02-29')
  expect(monthCells('2024-02-10').filter(Boolean)).toHaveLength(29)
  expect(monthCells('2026-10-07').filter(Boolean)).toHaveLength(31)
  expect(monthCells('2026-10-07').slice(0, 7)).toEqual([null, null, null, '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'])
  expect(monthCells('2026-10-07')[7]).toBe('2026-10-05')
  expect([0, 1, 4, 5, 14, 15, 29, 30].map(activityLevel)).toEqual([0, 1, 1, 2, 2, 3, 3, 4])
})
