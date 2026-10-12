'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import type { AssistantView } from '@/lib/assistant-api'

let current: AssistantView | null = null

// Page components publish IDs they already loaded; the server resolves names and access.
export function useAssistantView(nodeId?: string, wordId?: number | null) {
  const pathname = usePathname()
  useEffect(() => {
    const view: AssistantView = {
      path: window.location.pathname,
      ...(nodeId ? { node_id: nodeId } : {}),
      ...(wordId != null ? { word_id: wordId } : {}),
    }
    current = view
    return () => { if (current === view) current = null }
  }, [nodeId, wordId, pathname])
}

export function currentAssistantView(): AssistantView {
  const path = window.location.pathname
  return current?.path === path ? current : { path }
}
