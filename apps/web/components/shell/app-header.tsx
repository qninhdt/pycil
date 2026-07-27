"use client"

import { ActivityCenter } from "@/components/activity/activity-center"
import { ThemeToggle } from "@/components/theme/theme-toggle"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import { LAYER_CLASS } from "@/lib/design/layers"
import { MagnifyingGlassIcon } from "@/lib/icons"
import type { ViewerSummary } from "@/lib/auth/viewer"
import { useUiStore } from "@/lib/stores/store-provider"
import { cn } from "@/lib/utils"

import { AssistantTrigger } from "./assistant-slot"
import { UserMenu } from "./user-menu"

/**
 * Search opens the palette rather than navigating: search here always exists to
 * put a word into a deck, and a separate results page severs that intent.
 *
 * Two renderings of one control. Below `lg` the header is tight, so search is an
 * icon; from `lg` it is a labelled field-shaped button that can also show the
 * shortcut. Both are always in the markup and CSS picks one, so nothing swaps
 * after hydration.
 */
function SearchAction() {
  const openPalette = useUiStore((state) => state.openPalette)

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Search words"
        onClick={() => openPalette()}
        className="lg:hidden"
      >
        <MagnifyingGlassIcon />
      </Button>

      <Button
        variant="outline"
        onClick={() => openPalette()}
        className="hidden h-9 w-64 justify-start text-muted-foreground lg:inline-flex"
      >
        <MagnifyingGlassIcon data-icon="inline-start" />
        Search words
        {/* Announcing the shortcut to a screen reader is noise: the control is
            already reachable, and the keys are a pointer-user affordance. */}
        <Kbd aria-hidden className="ml-auto">
          ⌘K
        </Kbd>
      </Button>
    </>
  )
}

/**
 * The sticky header, present at every width. It is the only place in the app
 * with a backdrop blur, and `data-slot="app-header"` is what the
 * `prefers-reduced-transparency` rule in `globals.css` targets to drop it.
 *
 * The signed-out header keeps search and theme and offers sign-in, because the
 * library and sense routes are readable anonymously.
 */
export function AppHeader({
  viewer,
  assistantEnabled,
}: {
  viewer: ViewerSummary | null
  assistantEnabled: boolean
}) {
  return (
    <header
      data-slot="app-header"
      className={cn(
        "sticky top-0 flex h-14 items-center gap-1 border-b border-border px-4",
        "bg-background/85 supports-backdrop-filter:backdrop-blur-sm",
        LAYER_CLASS.stickyHeader,
      )}
    >
      {/* The rail carries the wordmark from `lg` up, so repeating it here would
          show it twice on desktop. */}
      <span className="font-serif text-lg font-semibold lg:hidden">Pycil</span>

      <div className="ml-auto flex items-center gap-1">
        <SearchAction />
        {viewer ? (
          <>
            <ActivityCenter />
            <AssistantTrigger enabled={assistantEnabled} />
            <ThemeToggle />
            <UserMenu viewer={viewer} />
          </>
        ) : (
          <>
            <ThemeToggle />
            <Button render={<a href="/api/auth/login" />} size="sm">
              Sign in
            </Button>
          </>
        )}
      </div>
    </header>
  )
}
