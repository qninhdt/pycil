"use client"

import { useEffect, useState } from "react"

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandList,
} from "@/components/ui/command"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { toast } from "@/components/ui/toast"
import { addSenseToDeck } from "@/lib/actions/words"
import { useIsMobile } from "@/hooks/use-mobile"
import { useUiStore } from "@/lib/stores/store-provider"

import { LiveSessionWarning } from "./live-session-warning"
import { PaletteCreateGroup } from "./palette-create-group"
import { PaletteNavigationGroup } from "./palette-navigation-group"
import { PaletteWordResults } from "./palette-word-results"

/** A sense the learner chose, held while the live-session warning is answered. */
interface PendingAdd {
  senseId: number
  headword: string
}

/**
 * The one search surface in the app.
 *
 * Full-height sheet on mobile, centred dialog on desktop. Both render through a
 * portal, so this branch is on `useIsMobile` rather than on a class: a hidden
 * wrapper would not contain a portal, and the inactive surface would sit over the
 * page. The trigger lives in the header, so the branch settling after mount is
 * not visible.
 */
export function CommandPalette() {
  const isMobile = useIsMobile()
  const open = useUiStore((state) => state.openSurface === "palette")
  const closeSurface = useUiStore((state) => state.closeSurface)
  const openPalette = useUiStore((state) => state.openPalette)
  const targetNodeId = useUiStore((state) => state.paletteTargetNodeId)
  const liveSession = useUiStore((state) => state.liveSession)
  const setLiveSession = useUiStore((state) => state.setLiveSession)

  const [query, setQuery] = useState("")
  const [pendingAdd, setPendingAdd] = useState<PendingAdd | null>(null)

  // The shortcut is global, so the listener lives with the surface it opens
  // rather than with the header button, which may not be mounted on study
  // routes. It is removed on unmount so a remount cannot bind it twice.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "k" || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      if (open) closeSurface()
      else openPalette()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [open, openPalette, closeSurface])

  const close = () => {
    closeSurface()
    // The query is cleared on close so the next open starts empty. Keeping it
    // would show stale results for a word the learner already dealt with.
    setQuery("")
    setPendingAdd(null)
  }

  const performAdd = async ({ senseId, headword }: PendingAdd) => {
    if (!targetNodeId) return
    const result = await addSenseToDeck(targetNodeId, senseId)

    if (!result.success) {
      toast.add({ title: `Could not add ${headword}`, description: result.error })
      return
    }

    // The add has just invalidated any live session, so the store stops claiming
    // one. Leaving it set would warn again about a session that is already over.
    if (liveSession) setLiveSession(null)
    toast.add({ title: `Added ${headword}` })
    close()
  }

  const onAddSense = (senseId: number, headword: string) => {
    // A live session makes this destructive, so it is confirmed rather than done.
    if (liveSession) {
      setPendingAdd({ senseId, headword })
      return
    }
    void performAdd({ senseId, headword })
  }

  const body = (
    <Command shouldFilter={false} className="bg-transparent">
      <CommandInput
        value={query}
        onValueChange={setQuery}
        placeholder="Search words, or jump to a screen"
      />
      <CommandList className="max-h-none flex-1 lg:max-h-96">
        {/* Only shown for an empty query: once something is typed, the results
            group and the generate fallback both speak for themselves. */}
        {query.trim().length === 0 ? (
          <CommandEmpty>Type to search for a word.</CommandEmpty>
        ) : null}
        <PaletteWordResults
          query={query}
          targetNodeId={targetNodeId}
          onAddSense={onAddSense}
          onNavigate={close}
        />
        <PaletteCreateGroup query={query} onSubmitted={close} />
        <PaletteNavigationGroup query={query} onNavigate={close} />
      </CommandList>
    </Command>
  )

  const onOpenChange = (next: boolean) => {
    if (!next) close()
  }

  return (
    <>
      {isMobile ? (
        <Sheet open={open} onOpenChange={onOpenChange}>
          <SheetContent
            side="bottom"
            className="flex h-[100dvh] flex-col gap-0 p-0 sm:max-w-none"
          >
            <SheetTitle className="sr-only">Search</SheetTitle>
            {body}
          </SheetContent>
        </Sheet>
      ) : (
        <Dialog open={open} onOpenChange={onOpenChange}>
          <DialogContent
            showCloseButton={false}
            className="top-[20%] max-w-lg translate-y-0 gap-0 p-0 sm:max-w-lg"
          >
            <DialogTitle className="sr-only">Search</DialogTitle>
            {body}
          </DialogContent>
        </Dialog>
      )}

      {liveSession && pendingAdd ? (
        <LiveSessionWarning
          liveSession={liveSession}
          open
          onConfirm={() => {
            const add = pendingAdd
            setPendingAdd(null)
            void performAdd(add)
          }}
          onCancel={() => setPendingAdd(null)}
        />
      ) : null}
    </>
  )
}
