'use client'

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import type { AssistantView } from '@/lib/api/assistant'

const ViewContext = createContext({ view: null as AssistantView | null, setView: (_view: AssistantView | null) => {}, getView: (): AssistantView => ({ path: window.location.pathname }) })
export function AssistantViewProvider({ children }: { children: React.ReactNode }) {
  const [view, setView] = useState<AssistantView | null>(null)
  const latest = useRef(view)
  useLayoutEffect(() => { latest.current = view }, [view])
  const getView = useCallback(() => latest.current?.path === window.location.pathname ? latest.current : { path: window.location.pathname }, [])
  return <ViewContext.Provider value={{ view, setView, getView }}>{children}</ViewContext.Provider>
}
export function useAssistantView(nodeId?: string, wordId?: number | null) {
  const pathname = usePathname(), { setView } = useContext(ViewContext)
  useEffect(() => {
    setView({ path: pathname ?? window.location.pathname, ...(nodeId ? { node_id: nodeId } : {}), ...(wordId != null ? { word_id: wordId } : {}) })
    return () => setView(null)
  }, [nodeId, wordId, pathname, setView])
}
export const useAssistantContext = () => useContext(ViewContext)
