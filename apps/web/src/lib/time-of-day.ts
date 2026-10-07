export type TimeOfDay = 'morning' | 'afternoon' | 'night'

export const timeOfDayStarts = { morning: 5, afternoon: 12, night: 18 } as const

export function getTimeOfDay(date: Date): TimeOfDay {
  const hour = date.getHours()
  if (hour < timeOfDayStarts.morning || hour >= timeOfDayStarts.night) return 'night'
  return hour < timeOfDayStarts.afternoon ? 'morning' : 'afternoon'
}

export function getNextTimeOfDayChange(date: Date): Date {
  for (const hour of Object.values(timeOfDayStarts)) {
    const boundary = new Date(date)
    boundary.setHours(hour, 0, 0, 0)
    if (boundary.getTime() > date.getTime()) return boundary
  }
  const tomorrow = new Date(date)
  tomorrow.setDate(tomorrow.getDate() + 1)
  tomorrow.setHours(timeOfDayStarts.morning, 0, 0, 0)
  return tomorrow
}
