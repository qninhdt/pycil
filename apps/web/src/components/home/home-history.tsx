'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { HomeResource } from '@/hooks/use-learning'
import type { StudyActivity, ReviewSchedule } from '@/lib/home-api'
import { activityLevel, dayLabel, eventCount, monthCells, shiftDay } from '@/lib/home-calendar'
import { HomeFailure, HomeLoading } from './home-state'

const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const intensityClasses = [
  'bg-secondary text-foreground',
  'bg-[color-mix(in_srgb,var(--palette-primary-blue)_15%,var(--palette-canvas))] text-[var(--palette-ink)]',
  'bg-[color-mix(in_srgb,var(--palette-primary-blue)_30%,var(--palette-canvas))] text-[var(--palette-ink)]',
  'bg-[color-mix(in_srgb,var(--palette-primary-blue)_45%,var(--palette-canvas))] text-[var(--palette-ink)]',
  'bg-[color-mix(in_srgb,var(--palette-primary-blue)_60%,var(--palette-canvas))] text-[var(--palette-ink)]'
]

export function HomeStreak({ activity, today }: { activity: HomeResource<StudyActivity>; today: string | null }) {
  const t = useTranslations('home')
  const data = activity.data
  return <section aria-labelledby="home-streak-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><h2 id="home-streak-title">{t('studyStreak')}</h2><span className="size-3.5 rounded-full bg-art-red" aria-hidden="true" /></div>
    {activity.status === 'loading' ? <HomeLoading label={t('studyStreakLabel')} /> : activity.status === 'error' ? <HomeFailure label={t('studyStreakLabel')} error={activity.error} retry={activity.retry} /> : data && today && <>
      <p className="home-streak-number flex items-baseline gap-3 my-8 mb-3 max-lg:mt-0 max-md:my-4 [&_strong]:text-7xl max-md:[&_strong]:text-5xl [&_strong]:font-extrabold [&_strong]:leading-none [&_strong]:tracking-tight [&_strong]:tabular-nums [&_>_span]:text-base"><strong>{data.current_streak}</strong><span>{data.current_streak === 1 ? t('day') : t('days')}</span></p>
      <div className="grid grid-cols-7 gap-2.5 my-7 max-lg:max-w-[320px] max-md:my-4 max-md:max-w-none max-md:gap-1.5 [&_>_div]:flex [&_>_div]:items-center [&_>_div]:flex-col [&_>_div]:gap-2.5 [&_span]:size-4.5 [&_span]:rounded-full [&_span]:bg-border [&_span]:border [&_span]:border-border [&_[data-active=true]_span]:bg-art-red [&_[data-active=true]_span]:border-art-red [&_[data-today=true]_span]:outline [&_[data-today=true]_span]:outline-1 [&_[data-today=true]_span]:outline-foreground [&_[data-today=true]_span]:outline-offset-[3px] [&_small]:text-[11px] [&_small]:text-muted-foreground" aria-label={t('activitySevenDaysAria')}>{Array.from({ length: 7 }, (_, index) => {
        const date = shiftDay(today, index - 6)
        const day = data.days.find(day => day.day === date)!
        const active = eventCount(day) > 0
        return <div key={date} data-active={active} data-today={date === today} aria-label={`${dayLabel(date)}: ${active ? t('active') : t('noActivity')}`}><span aria-hidden="true" /><small>{dayLabel(date, { weekday: 'short' }).slice(0, 1)}</small></div>
      })}</div>
      <p className="border-t border-border pt-4.5 flex justify-between gap-3 text-xs text-muted-foreground [&_strong]:text-foreground">{t('longestStreak')}<strong>{data.longest_streak} {data.longest_streak === 1 ? t('day') : t('days')}</strong></p>
    </>}
  </section>
}

export function HomeActivity({ activity, today }: { activity: HomeResource<StudyActivity>; today: string | null }) {
  const t = useTranslations('home')
  const tCommon = useTranslations('common')
  const [selected, setSelected] = useState<string | null>(null)
  const data = activity.data
  const days = new Map(data?.days.map(day => [day.day, day]) ?? [])
  const month = today?.slice(0, 7)
  const activeDays = data?.days.filter(day => day.day.startsWith(month!) && eventCount(day) > 0).length ?? 0
  const events = data?.days.filter(day => day.day.startsWith(month!)).reduce((sum, day) => sum + eventCount(day), 0) ?? 0
  const selectedDay = selected && days.get(selected)

  return <section aria-labelledby="home-activity-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><h2 id="home-activity-title">{t('studyActivity')}</h2>{today && <span className="text-[13px] text-muted-foreground leading-relaxed">{dayLabel(today, { month: 'long', year: 'numeric' })}</span>}</div>
    {activity.status === 'loading' ? <HomeLoading label={t('studyActivityLabel')} /> : activity.status === 'error' ? <HomeFailure label={t('studyActivityLabel')} error={activity.error} retry={activity.retry} /> : data && today && <>
      <div className="flex flex-wrap gap-6 text-[13px] mb-6 [&_strong]:text-2xl [&_strong]:font-extrabold [&_strong]:tabular-nums [&_strong]:mr-1.5"><p><strong>{activeDays}</strong> {t('activeDays')}</p><p><strong>{events.toLocaleString('en')}</strong> {t('learningEvents')}</p></div>
      <div className="grid gap-2 w-full max-w-[448px]"><div className="home-calendar-weekdays grid grid-cols-7 gap-2 text-center text-muted-foreground text-[11px] max-md:gap-1" aria-hidden="true">{weekdays.map((day, index) => <span key={index}>{day}</span>)}</div>
        <div className="home-calendar grid grid-cols-7 gap-2 max-md:gap-1" aria-label={t('monthlyActivityAria')}>{monthCells(today).map((date, index) => {
          if (!date) return <span key={`blank-${index}`} className="aspect-square min-w-0" aria-hidden="true" />
          const future = date > today
          const day = days.get(date)
          const events = day ? eventCount(day) : 0
          const label = `${dayLabel(date, { weekday: 'long', month: 'short', day: 'numeric' })}: ${future ? t('upcomingDay') : events === 1 ? t('learningEventSingular') : t('learningEventsPlural', { events })}`
          return <Tooltip key={date}><TooltipTrigger asChild><button type="button" data-calendar-day className={`home-calendar-day aspect-square min-w-0 flex items-center justify-center border border-border rounded-none text-xs font-[650] tabular-nums transition-[outline-color] duration-120 data-[future=true]:bg-transparent data-[future=true]:border-dashed data-[future=true]:text-muted-foreground data-[today=true]:border-foreground not-disabled:hover:outline not-disabled:hover:outline-2 not-disabled:hover:outline-foreground not-disabled:hover:outline-offset-1 aria-pressed:outline aria-pressed:outline-2 aria-pressed:outline-foreground aria-pressed:outline-offset-1 ${future ? "" : intensityClasses[activityLevel(events)]}`} data-level={activityLevel(events)} data-future={future} data-today={date === today} aria-current={date === today ? 'date' : undefined} aria-label={label} aria-pressed={selected === date} disabled={future} onClick={() => setSelected(date)}><span aria-hidden="true">{Number(date.slice(-2))}</span></button></TooltipTrigger><TooltipContent>{label}</TooltipContent></Tooltip>
        })}</div>
        <div className="flex justify-end items-center gap-1 text-[10px] text-muted-foreground mt-2 [&_i]:size-3 [&_i]:border [&_i]:border-border [&_>_span:first-child]:mr-1.5 [&_>_span:last-child]:ml-1.5" aria-label={t('activityIntensity')}><span>{tCommon('less')}</span>{[0, 1, 2, 3, 4].map(level => <i key={level} className={intensityClasses[level]} aria-hidden="true" />)}<span>{tCommon('more')}</span></div>
      </div>
      {(selectedDay || events === 0) && <p className="home-activity-detail text-xs leading-relaxed text-muted-foreground mt-4 max-w-[64ch]" role="status">{selectedDay ? t('activityResultsDetail', { date: dayLabel(selectedDay.day), scheduled: selectedDay.applied_events, practice: selectedDay.practice_events }) : t('noActivityThisMonth')}</p>}
    </>}
  </section>
}

export function HomeSchedule({ schedule, today }: { schedule: HomeResource<ReviewSchedule>; today: string | null }) {
  const t = useTranslations('home')
  const data = schedule.data
  const largest = Math.max(1, ...(data?.days.map(day => day.count) ?? []))
  const total = data?.days.reduce((sum, day) => sum + day.count, 0) ?? 0

  return <section aria-labelledby="home-schedule-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><h2 id="home-schedule-title">{t('upcomingReviews')}</h2><span className="text-[13px] text-muted-foreground leading-relaxed">{t('next7Days')}</span></div>
    {schedule.status === 'loading' ? <HomeLoading label={t('reviewScheduleLabel')} /> : schedule.status === 'error' ? <HomeFailure label={t('reviewScheduleLabel')} error={schedule.error} retry={schedule.retry} /> : data && <>
      <ol className="home-schedule-list my-2 mb-5 [&_>_li]:grid [&_>_li]:grid-cols-[78px_minmax(0,1fr)_40px] [&_>_li]:gap-4 [&_>_li]:items-center [&_>_li]:py-3 [&_>_li]:border-b [&_>_li]:border-border [&_>_li]:text-xs [&_time]:whitespace-nowrap [&_strong]:text-right [&_strong]:tabular-nums">{data.days.map(day => <li key={day.day}><time dateTime={day.day}>{day.day === today ? t('laterToday') : day.day === shiftDay(today!, 1) ? t('tomorrow') : dayLabel(day.day, { weekday: 'short', day: 'numeric' })}</time><span className="h-1.5 bg-secondary [&_>_i]:h-full [&_>_i]:block [&_>_i]:bg-art-blue" aria-hidden="true"><i style={{ width: `${day.count / largest * 100}%` }} /></span><strong>{day.count.toLocaleString('en')}<span className="sr-only"> {t('meanings')}</span></strong></li>)}</ol>
      {total === 0 && <p className="text-[13px] text-muted-foreground leading-relaxed">{t('noFutureReviews')}</p>}
    </>}
  </section>
}
