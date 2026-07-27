import { createApiClient } from "@/lib/api/client"
import { getSession } from "@/lib/auth/session"
import { toViewerSummary } from "@/lib/auth/viewer"
import { AppShell } from "@/components/shell/app-shell"

/**
 * Chrome only. Every provider is mounted in the root layout instead, so `/study`
 * — which sits outside this group and renders no chrome — still reads the same
 * store, query cache, and realtime connection as the shell.
 *
 * Only `ViewerSummary` crosses into the client tree. `getSession()` also holds
 * the access and refresh tokens, and handing that object down would serialise
 * both into the RSC payload in plaintext.
 */
export default async function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getSession()
  const viewer = toViewerSummary(session)

  // The capability read is what decides whether the assistant exists at all, so
  // a failed read has to mean "absent" rather than a crashed shell. The endpoint
  // needs no caller, which is why the anonymous library view resolves it too.
  let assistantEnabled = false
  try {
    const capabilities = await createApiClient(session).getCapabilities()
    assistantEnabled = capabilities.assistant
  } catch {
    assistantEnabled = false
  }

  return (
    <AppShell viewer={viewer} assistantEnabled={assistantEnabled}>
      {children}
    </AppShell>
  )
}
