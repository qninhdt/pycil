"use client"

import { useEffect, useState } from "react"

import { createApiClient } from "@/lib/api/client"
import type { Viewer } from "@/lib/api/types"

import { AppShell } from "./app-shell"

export function AppClientLayout({ children }: { children: React.ReactNode }) {
  const [viewer, setViewer] = useState<Viewer | null>(null)
  const [assistantEnabled, setAssistantEnabled] = useState(false)

  useEffect(() => {
    const client = createApiClient()
    void Promise.all([client.auth.getViewer(), client.auth.getCapabilities()])
      .then(([nextViewer, capabilities]) => {
        setViewer(nextViewer)
        setAssistantEnabled(capabilities.assistant)
      })
      .catch(() => {
        setViewer(null)
        setAssistantEnabled(false)
      })
  }, [])

  return (
    <AppShell viewer={viewer} assistantEnabled={assistantEnabled}>
      {children}
    </AppShell>
  )
}
