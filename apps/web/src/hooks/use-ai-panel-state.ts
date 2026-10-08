'use client'

import { useSyncExternalStore } from 'react'
import { aiOpenKey } from '@/lib/ui-preferences'

function getAiSnapshot() {
  if (typeof document === 'undefined') return false
  return document.documentElement.dataset.aiOpen === 'true'
}

function subscribeAi(callback: () => void) {
  const observer = new MutationObserver(callback)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-ai-open'] })
  const storage = (event: StorageEvent) => {
    if (event.key === aiOpenKey || event.key === null) {
      document.documentElement.dataset.aiOpen = event.newValue === 'true' ? 'true' : 'false'
    }
  }
  window.addEventListener('storage', storage)
  return () => {
    observer.disconnect()
    window.removeEventListener('storage', storage)
  }
}

export function useAiPanelState() {
  const open = useSyncExternalStore(subscribeAi, getAiSnapshot, () => false)
  const setOpen = (value: boolean) => {
    const next = String(value)
    document.documentElement.dataset.aiOpen = next
    try {
      localStorage.setItem(aiOpenKey, next)
    } catch {
      /* Storage is optional */
    }
  }
  const toggle = () => setOpen(!getAiSnapshot())
  return { open, setOpen, toggle }
}
