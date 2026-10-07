export function reportingDay(now: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat('en', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now)
  const part = (name: string) => parts.find(value => value.type === name)!.value
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function shiftDay(day: string, offset: number): string {
  const date = new Date(`${day}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() + offset)
  return date.toISOString().slice(0, 10)
}

export function dayLabel(day: string, options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }): string {
  return new Intl.DateTimeFormat('en', { ...options, timeZone: 'UTC' }).format(new Date(`${day}T12:00:00Z`))
}

export function monthCells(today: string): (string | null)[] {
  const first = `${today.slice(0, 7)}-01`
  const date = new Date(`${first}T12:00:00Z`)
  const padding = (date.getUTCDay() + 6) % 7
  const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate()
  const cells = Array.from({ length: Math.ceil((padding + last) / 7) * 7 }, (_, index) =>
    index < padding || index >= padding + last ? null : shiftDay(first, index - padding))
  return cells
}

export const eventCount = (day: { applied_events: number; practice_events: number }) => day.applied_events + day.practice_events
export const activityLevel = (events: number) => events === 0 ? 0 : events < 5 ? 1 : events < 15 ? 2 : events < 30 ? 3 : 4
