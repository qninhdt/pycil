import { AppHeader } from "./app-header"
import { BottomTabBar } from "./bottom-tab-bar"
import { CommandPalette } from "@/components/command/command-palette"
import { NavRail } from "./nav-rail"
import type { ViewerSummary } from "@/lib/auth/viewer"

/**
 * The frame every screen except study lives in.
 *
 * This is a Server Component: it holds no state of its own, and keeping it on
 * the server means the viewer projection never has to cross a client boundary
 * more than once. The interactive parts below it are their own client leaves.
 *
 * Offsets are stated here rather than by each page. The rail is fixed, so
 * content needs a left margin from `lg` up; the tab bar is fixed, so content
 * needs bottom padding below `lg`. A page that set its own would drift.
 */
export function AppShell({
  viewer,
  assistantEnabled,
  children,
}: {
  viewer: ViewerSummary | null
  assistantEnabled: boolean
  children: React.ReactNode
}) {
  return (
    <div className="min-h-dvh lg:pl-56">
      <NavRail />
      <AppHeader viewer={viewer} assistantEnabled={assistantEnabled} />

      {/* max-w rather than mx-auto: the content column is left-aligned in the
          space beside the rail, never centred in the viewport. */}
      <main className="mx-0 w-full max-w-[1120px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12 lg:pb-12">
        {children}
      </main>

      <BottomTabBar />
      {/* Mounted once here so `Cmd/Ctrl K` works on every shell screen. */}
      <CommandPalette />
    </div>
  )
}
