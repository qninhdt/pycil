"use client"

import { useEffect, useState } from "react"

import { AppearanceCard } from "@/components/settings/appearance-card"
import { DataExportCard } from "@/components/settings/data-export-card"
import { DeleteAccountDialog } from "@/components/settings/delete-account-dialog"
import { ProfileCard } from "@/components/settings/profile-card"
import { SessionShapeForm } from "@/components/settings/session-shape-form"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { readLearningSettings, readViewer } from "@/lib/actions/settings-reads"
import type { LearningSettings, Viewer } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

export default function SettingsPage() {
  const [viewer, setViewer] = useState<Viewer | null>(null)
  const [settings, setSettings] = useState<LearningSettings | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    void Promise.all([readViewer(), readLearningSettings()])
      .then(([nextViewer, nextSettings]) => {
        setViewer(nextViewer)
        setSettings(nextSettings)
      })
      .catch(() => setFailed(true))
  }, [])

  if (failed) return <p className="text-sm text-muted-foreground">Settings could not load. Try again.</p>
  if (!viewer || !settings) return <Spinner aria-label="Loading settings" />

  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <h1 className="text-2xl tracking-tight">Settings</h1>
      <ProfileCard viewer={viewer} />
      <AppearanceCard />
      <Card>
        <CardHeader>
          <CardTitle>Session shape</CardTitle>
          <CardDescription>How long a session runs and how it is broken into rounds. These apply to every deck you study.</CardDescription>
        </CardHeader>
        <CardContent><SessionShapeForm settings={settings} /></CardContent>
      </Card>
      <DataExportCard />
      <Card>
        <CardHeader>
          <CardTitle>Delete account</CardTitle>
          <CardDescription>Removing your account erases your decks and your whole review history. Export your data first if you want to keep a copy.</CardDescription>
        </CardHeader>
        <CardContent><DeleteAccountDialog /></CardContent>
      </Card>
    </div>
  )
}
