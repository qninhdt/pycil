"use client"

/**
 * The assistant itself: a bottom drawer on mobile, a right sidebar on desktop.
 *
 * Not a navigation destination, because it is a tool that acts on the library rather
 * than a place to go. Leaving Today to reach it would mean leaving the thing being
 * discussed.
 *
 * The two renderings are a genuine branch rather than responsive classes. The drawer
 * renders through a portal, so a `lg:hidden` wrapper would not contain it — the portal
 * escapes and the content sits over the page at every width. The sidebar, by contrast,
 * must be *in* the layout flow so it can shrink the content column, which a portal
 * cannot do. One cannot be the other with CSS.
 *
 * Which is exactly why neither owns the conversation. They are mutually exclusive by
 * viewport, so crossing 1024px unmounts one and mounts the other; state held in either
 * would be lost mid-turn by a rotated tablet or a dragged window. The conversation
 * lives in the assistant store and these render it.
 */

import { useEffect } from "react"

import { Button } from "@/components/ui/button"
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer"
import { useIsBelowDesktop } from "@/hooks/use-mobile"
import { listThreads } from "@/lib/actions/assistant"
import { XIcon } from "@/lib/icons"
import type { AssistantStore } from "@/lib/stores/assistant-store"
import { useAssistantStore, useAssistantStoreApi, useUiStore } from "@/lib/stores/store-provider"
import { cn } from "@/lib/utils"

import { AssistantErrorNotice } from "./assistant-error-notice"
import { AssistantChat } from "./assistant-chat"
import { ThreadList } from "./thread-list"

/**
 * Everything inside the surface, independent of which container holds it.
 *
 * Written once because the drawer and the sidebar differ only in their frame. The
 * conversation, its transport, and its failure states are identical.
 */
function AssistantBody() {
  const store = useAssistantStoreApi()
  const threads = useAssistantStore((state) => state.threads)
  const listProblem = useAssistantStore((state) => state.listProblem)
  const threadId = useAssistantStore((state) => state.openThreadId)
  const listRead = useAssistantStore((state) => state.listRead)
  const listLoaded = useAssistantStore((state) => state.listLoaded)

  useEffect(() => {
    if (listLoaded) return
    store.getState().setListLoaded(true)
    void refreshThreads(store).then((ok) => {
      if (!ok) store.getState().setListLoaded(false)
    })
  }, [listLoaded, store])

  const openThreadId = threadId && (!listRead || threads.some((thread) => thread.id === threadId))
    ? threadId
    : null

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {listProblem ? <AssistantErrorNotice code={listProblem} /> : null}
      <ThreadList
        threads={threads}
        activeThreadId={openThreadId}
        onOpen={(id) => store.getState().openThread(id)}
        onChanged={() => void refreshThreads(store)}
      />
      {openThreadId ? <AssistantChat /> : null}
    </div>
  )
}

/**
 * Reads the thread list into the store. Returns whether it succeeded.
 *
 * A failed *action* returns a code rather than throwing, so the failure is inside the
 * resolved value; a thrown one is transport. Both have to surface, and neither may
 * clear a list already on screen — a failed refresh after a delete should say so
 * beside the conversations, not replace them with nothing.
 *
 * The boolean is what lets the caller retry. A failed first read that recorded
 * itself as done would leave the list permanently empty, and an empty list means no
 * thread can be opened at all.
 */
async function refreshThreads(store: AssistantStore): Promise<boolean> {
  const result = await listThreads()
  const state = store.getState()
  if (result.success) {
    state.setThreads(result.data, null)
    return true
  }
  state.setThreads(state.threads, result.code, false)
  return false
}

/**
 * The narrow rendering: a bottom drawer.
 *
 * Separate export from the sidebar because the two are structurally different, not
 * two styles of one thing. A drawer renders through a portal, so it may be mounted
 * anywhere in the tree; the sidebar must sit in the layout flow beside the content
 * column, which a portal cannot do. Trying to serve both from one component is what
 * produced a desktop sidebar that overlaid the page instead of shrinking it.
 *
 * Below `lg` to match the shell: the nav rail appears at `lg`, so anything switching
 * at `md` would render the desktop sidebar while the bottom tab bar was still there,
 * and the two would collide.
 */
export function AssistantDrawer() {
  const isCompact = useIsBelowDesktop()
  const open = useUiStore((state) => state.openSurface === "assistant")
  const openAssistant = useUiStore((state) => state.openAssistant)
  const closeSurface = useUiStore((state) => state.closeSurface)

  if (!isCompact) return null

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => (next ? openAssistant() : closeSurface())}
    >
      {/* No `DrawerTrigger`: the trigger lives in the header and is wired
          through the store instead. */}
      <DrawerContent
        // Capped rather than full height so the composer stays clear of the on-screen
        // keyboard at 320px. `dvh` follows the visual viewport, which is what shrinks
        // when the keyboard opens.
        className="max-h-[85dvh]"
      >
        <DrawerHeader>
          {/* Required: a drawer with no accessible name is announced as an unlabelled
              dialog, leaving a screen reader user with no idea what opened. */}
          <DrawerTitle>Assistant</DrawerTitle>
        </DrawerHeader>
        <div className="flex min-h-0 flex-1 flex-col px-4 pb-4">
          <AssistantBody />
        </div>
      </DrawerContent>
    </Drawer>
  )
}

/**
 * The wide rendering: a column beside the content, not over it.
 *
 * In normal flow and `sticky` rather than `fixed`, which is the whole point. An
 * in-flow column takes width from its flex parent, so opening it *shrinks* the
 * content column — the behaviour the design asks for — and it needs no `z-index`,
 * because nothing overlaps it to begin with.
 *
 * `fixed` fails here three ways, and did: it is out of flow so it cannot shrink
 * anything; it resolves against the nearest ancestor with a filter or transform
 * rather than the viewport, which the blurred header is; and it inherits that
 * header's stacking context, so the bottom tab bar painted over it.
 *
 * `sticky top-14` keeps it in view under the sticky header while the page scrolls,
 * which is what `fixed` was reaching for.
 */
export function AssistantSidebar() {
  const isCompact = useIsBelowDesktop()
  const open = useUiStore((state) => state.openSurface === "assistant")
  const closeSurface = useUiStore((state) => state.closeSurface)

  // Absent rather than zero-width when closed: a collapsed flex item still
  // contributes its border and gap, leaving a seam beside the content.
  if (isCompact || !open) return null

  return (
    <aside
      aria-label="Assistant"
      className={cn(
        "sticky top-14 flex h-[calc(100dvh-3.5rem)] w-96 shrink-0 flex-col gap-3",
        "border-l border-border bg-background p-4",
      )}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Assistant</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close assistant"
          onClick={closeSurface}
        >
          <XIcon />
        </Button>
      </div>
      <AssistantBody />
    </aside>
  )
}
