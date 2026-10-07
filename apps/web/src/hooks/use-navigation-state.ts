'use client'

import { useSyncExternalStore } from 'react'
import { navigationCollapsedKey } from '@/lib/ui-preferences'

function getSnapshot() {
  return document.documentElement.dataset.navigationCollapsed === 'true'
}

function subscribe(callback: () => void) {
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-navigation-collapsed'] })
  const storage = (event: StorageEvent) => {
    if (event.key === navigationCollapsedKey || event.key === null) {
      document.documentElement.dataset.navigationCollapsed = event.newValue === 'true' ? 'true' : 'false'
    }
  }
  window.addEventListener('storage', storage)
  return () => { observer.disconnect(); window.removeEventListener('storage', storage) }
}

function toggleCollapsed() {
  const next = String(!getSnapshot())
  document.documentElement.dataset.navigationCollapsed = next
  try { localStorage.setItem(navigationCollapsedKey, next) } catch { /* Collapse still works when storage is unavailable. */ }
}

export function useNavigationState() {
  const collapsed = useSyncExternalStore(subscribe, getSnapshot, () => false)
  return { collapsed, toggleCollapsed }
}
