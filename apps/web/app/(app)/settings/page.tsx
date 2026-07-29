import type { Metadata } from "next"

import { AppearanceCard } from "@/components/settings/appearance-card"
import { DataExportCard } from "@/components/settings/data-export-card"
import { SessionShapeForm } from "@/components/settings/session-shape-form"
import { DeleteAccountDialog } from "@/components/settings/delete-account-dialog"
import { ProfileCard } from "@/components/settings/profile-card"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { readLearningSettings, readViewer } from "@/lib/actions/settings-reads"

export const metadata: Metadata = { title: "Settings" }

/**
 * Profile, appearance, session shape, and the account itself.
 *
 * Session shape is one form because it is one setting on the account. It used to be
 * per deck, which meant the same person got a different session length depending on
 * which deck they opened, and a session started on a folder ignored the values
 * altogether. Reaching them also required walking the whole node tree, since the API
 * pages children one level at a time and has no flat deck listing.
 */
export default async function SettingsPage() {
  // Both reads are independent, so they overlap. A failure in either is left to the
  // route's error boundary: a settings screen with no profile and no values is a blank
  // frame of section headings, which is worse than one stated error.
  const [viewer, learningSettings] = await Promise.all([
    readViewer(),
    readLearningSettings(),
  ])

  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <h1 className="text-2xl tracking-tight">Settings</h1>

      <ProfileCard viewer={viewer} />

      <AppearanceCard />

      <Card>
        <CardHeader>
          <CardTitle>Session shape</CardTitle>
          <CardDescription>
            How long a session runs and how it is broken into rounds. These apply to
            every deck you study.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SessionShapeForm settings={learningSettings} />
        </CardContent>
      </Card>

      <DataExportCard />

      <Card>
        <CardHeader>
          <CardTitle>Delete account</CardTitle>
          <CardDescription>
            Removing your account erases your decks and your whole review history. Export
            your data first if you want to keep a copy.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DeleteAccountDialog />
        </CardContent>
      </Card>
    </div>
  )
}
