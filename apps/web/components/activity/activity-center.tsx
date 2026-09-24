"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"
import { Empty, EmptyDescription, EmptyTitle } from "@/components/ui/empty"
import {
  Popover,
  PopoverContent,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useIsMobile } from "@/hooks/use-mobile"
import { BellIcon } from "@/lib/icons"
import { useActivitySubscriptions } from "@/lib/jobs/use-activity-subscriptions"
import { isUnsettled } from "@/lib/stores/activity-store"
import {
  useActivityActions,
  useActivityStore,
  useUiStore,
} from "@/lib/stores/store-provider"

import { ActivityTaskRow } from "./activity-task-row"

/**
 * The bell and its unsettled count.
 *
 * Returned as children of the trigger rather than as the trigger itself. A
 * custom component handed to `render` receives the props the trigger injects —
 * the click handler, the ref, `aria-expanded` — and has to spread them; this one
 * took only `unsettledCount`, so it dropped all of them and the surface could
 * never open. Every other `render` in the app passes a primitive that spreads,
 * which is why this was the only one affected.
 */
function ActivityTriggerContent({ unsettledCount }: { unsettledCount: number }) {
  return (
    <>
      <BellIcon />
      {unsettledCount > 0 ? (
        <Badge
          aria-hidden
          className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-1 text-[0.625rem]"
        >
          {unsettledCount}
        </Badge>
      ) : null}
      {unsettledCount > 0 ? (
        <span className="sr-only">{unsettledCount} in progress</span>
      ) : null}
    </>
  )
}

/** The trigger element itself, shared by the drawer and the popover. */
const activityTriggerButton = (
  <Button variant="ghost" size="icon" aria-label="Activity" className="relative" />
)

function ActivityBody() {
  const tasks = useActivityStore((state) => state.tasks)
  const { dismiss } = useActivityActions()

  return (
    <div className="flex flex-col gap-3">
      {tasks.length === 0 ? (
        <Empty className="border-none py-6">
          <EmptyTitle>Nothing running</EmptyTitle>
          <EmptyDescription>
            Generated words and graded answers show up here while they work.
          </EmptyDescription>
        </Empty>
      ) : (
        // The row is the list item, so it is not wrapped in another one here.
        <ul className="flex flex-col divide-y divide-border">
          {tasks.map((task) => (
            <ActivityTaskRow key={task.taskId} task={task} onDismiss={dismiss} />
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Bottom drawer on mobile, popover on desktop.
 *
 * This is one of the few genuinely non-CSS branches in the shell: both surfaces
 * render through a portal, so a `lg:hidden` wrapper would not hide the one that
 * is meant to be inactive — the portal escapes it and the content would sit on
 * top of the page. The trigger is the same `Button` either way, so the decision
 * settling after mount is not visible.
 *
 * The subscription effect lives here rather than in the surface so a task keeps
 * settling while the surface is closed.
 */
export function ActivityCenter() {
  useActivitySubscriptions()

  const isMobile = useIsMobile()
  const open = useUiStore((state) => state.openSurface === "activity")
  const openActivity = useUiStore((state) => state.openActivity)
  const closeSurface = useUiStore((state) => state.closeSurface)
  const unsettledCount = useActivityStore(
    (state) => state.tasks.filter(isUnsettled).length,
  )

  const onOpenChange = (next: boolean) => (next ? openActivity() : closeSurface())

  if (isMobile) {
    return (
      <Drawer open={open} onOpenChange={onOpenChange}>
        <DrawerTrigger render={activityTriggerButton}>
          <ActivityTriggerContent unsettledCount={unsettledCount} />
        </DrawerTrigger>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle>Activity</DrawerTitle>
          </DrawerHeader>
          <div className="overflow-y-auto px-4 pb-6">
            <ActivityBody />
          </div>
        </DrawerContent>
      </Drawer>
    )
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger render={activityTriggerButton}>
        <ActivityTriggerContent unsettledCount={unsettledCount} />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-88">
        <PopoverTitle>Activity</PopoverTitle>
        <ActivityBody />
      </PopoverContent>
    </Popover>
  )
}
