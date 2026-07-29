import {
  AssistantDrawer,
  AssistantSidebar,
} from "@/components/assistant/assistant-surface"
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

      {/* A flex row so the assistant can take width *from* the content column
          rather than sitting on top of it. `items-start` keeps the sidebar at its
          own height, which is what lets it stick; the default `stretch` would size
          it to the whole page and `position: sticky` would have nothing to do. */}
      <div className="flex items-start">
        {/* max-w rather than mx-auto: the content column is left-aligned in the
            space beside the rail, never centred in the viewport. `min-w-0` because
            a flex item defaults to `min-width: auto` and would refuse to shrink
            below its content, pushing the sidebar off-screen instead of narrowing. */}
        <main className="mx-0 min-w-0 w-full max-w-[1120px] flex-1 px-4 pt-8 pb-24 lg:px-8 lg:pt-12 lg:pb-12">
          {children}
        </main>

        {/* In the row, so opening it shrinks `main`. It renders nothing below `lg`
            or while closed. */}
        <AssistantSidebar />
      </div>

      <BottomTabBar />
      {/* The narrow rendering. Portalled, so its position here is immaterial; it is
          mounted beside the shell rather than inside the header so that the header
          does not become a containing block for it. */}
      <AssistantDrawer />
      {/* Mounted once here so `Cmd/Ctrl K` works on every shell screen. */}
      <CommandPalette />
    </div>
  )
}
