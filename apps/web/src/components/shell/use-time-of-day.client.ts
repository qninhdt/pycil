'use client'

import { useSyncExternalStore } from 'react'
import { getNextTimeOfDayChange, getTimeOfDay, type TimeOfDay } from '@/lib/time-of-day'

function getSnapshot(): TimeOfDay {
  const period = document.documentElement.dataset.timeOfDay
  return period === 'afternoon' || period === 'night' ? period : 'morning'
}

function subscribe(callback: () => void) {
  let timer: number | undefined
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-time-of-day'] })
  const refresh = () => {
    window.clearTimeout(timer)
    const now = new Date()
    const period = getTimeOfDay(now)
    if (document.documentElement.dataset.timeOfDay !== period) document.documentElement.dataset.timeOfDay = period
    // The boundary fires exactly on time; minute checks also handle clock/timezone changes.
    timer = window.setTimeout(refresh, Math.min(60000, Math.max(1, getNextTimeOfDayChange(now).getTime() - now.getTime())))
  }
  const visibility = () => {
    if (document.visibilityState === 'visible') refresh()
    else window.clearTimeout(timer)
  }
  refresh()
  document.addEventListener('visibilitychange', visibility)
  window.addEventListener('focus', refresh)
  return () => {
    window.clearTimeout(timer)
    observer.disconnect()
    document.removeEventListener('visibilitychange', visibility)
    window.removeEventListener('focus', refresh)
  }
}

export function useTimeOfDay(): TimeOfDay {
  return useSyncExternalStore(subscribe, getSnapshot, () => 'morning')
}
