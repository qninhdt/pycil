'use client'

import { useLayoutEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'

export function useWorkspaceScroll() {
  const pathname = usePathname()
  const workspace = useRef<HTMLDivElement>(null)
  const positions = useRef(new Map<string, number>())

  useLayoutEffect(() => {
    const element = workspace.current
    if (!element) return
    // The router restores the document, but this shared pane owns the app's scroll.
    const entry = window.history.state?.pycilWorkspaceEntry ?? crypto.randomUUID()
    window.history.replaceState({ ...window.history.state, pycilWorkspaceEntry: entry }, '')
    const top = positions.current.get(entry) ?? (window.location.hash ? element.scrollTop : 0)
    let restoring = true
    const observer = new ResizeObserver(restore)

    function restore() {
      element!.scrollTop = top
      if (element!.scrollTop === top) {
        restoring = false
        observer.disconnect()
      }
    }
    function remember() {
      if (!restoring) positions.current.set(entry, element!.scrollTop)
    }
    function stopRestoring() {
      restoring = false
      observer.disconnect()
      remember()
    }

    restore()
    const content = element.querySelector('main')
    if (restoring && content) observer.observe(content)
    element.addEventListener('scroll', remember)
    element.addEventListener('wheel', stopRestoring, { passive: true })
    element.addEventListener('touchstart', stopRestoring, { passive: true })
    element.addEventListener('pointerdown', stopRestoring)
    element.addEventListener('keydown', stopRestoring)
    return () => {
      observer.disconnect()
      element.removeEventListener('scroll', remember)
      element.removeEventListener('wheel', stopRestoring)
      element.removeEventListener('touchstart', stopRestoring)
      element.removeEventListener('pointerdown', stopRestoring)
      element.removeEventListener('keydown', stopRestoring)
    }
  }, [pathname])

  return workspace
}
