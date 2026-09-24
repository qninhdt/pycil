"use client"

import Link from "next/link"
import { useClerk } from "@clerk/nextjs"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { GearIcon, SignOutIcon } from "@/lib/icons"
import type { ViewerSummary } from "@/lib/auth/viewer"

/** First letter of the display name, or of the address when there is no name. */
function initial(viewer: ViewerSummary): string {
  const source = viewer.name?.trim() || viewer.email
  return source.slice(0, 1).toUpperCase()
}

/**
 * Avatar menu: settings and sign-out, and nothing else. Destinations belong in
 * the rail and the tab bar, so putting one here would make four.
 *
 * Sign-out is Clerk's, because Clerk is the only issuer of the session. Calling a
 * Pycil endpoint would not end the session the API actually validates, so the
 * learner would appear signed out here while their bearer token still worked.
 */
export function UserMenu({ viewer }: { viewer: ViewerSummary }) {
  const clerk = useClerk()

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant="ghost" size="icon" aria-label="Account" />}
        >
          <Avatar size="sm">
            {viewer.image ? <AvatarImage src={viewer.image} alt="" /> : null}
            <AvatarFallback>{initial(viewer)}</AvatarFallback>
          </Avatar>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="flex flex-col gap-0.5">
            {viewer.name ? <span>{viewer.name}</span> : null}
            <span className="truncate text-xs font-normal text-muted-foreground">
              {viewer.email}
            </span>
          </DropdownMenuLabel>

          <DropdownMenuSeparator />

          <DropdownMenuGroup>
            <DropdownMenuItem render={<Link href="/settings" />}>
              <GearIcon />
              Settings
            </DropdownMenuItem>
          </DropdownMenuGroup>

          <DropdownMenuSeparator />

          <DropdownMenuGroup>
            <DropdownMenuItem
              onClick={() => {
                void clerk.signOut({ redirectUrl: "/login" })
              }}
            >
              <SignOutIcon />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

    </>
  )
}
