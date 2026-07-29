import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { InfoIcon } from "@/lib/icons"

/**
 * Shown to a signed-out reader who followed a shared link.
 *
 * The API serves a public node, its deck items, and a sense record to a caller with
 * no account, so this page is genuinely readable — it is simply read-only. Saying
 * that once, at the top, is what makes the absence of every edit control read as
 * intentional rather than as a screen that failed to finish loading.
 *
 * The call to action carries no return path. This node may be private to whoever
 * signs in next, and bouncing them to a 404 after a successful sign-in is worse
 * than landing them somewhere that certainly works.
 */
export function AnonymousReadNotice() {
  return (
    <Alert>
      <InfoIcon />
      <AlertTitle>You are reading a shared item</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3">
        <span>
          Sign in to keep your own decks, track what you have learned, and study
          from lists like this one.
        </span>
        <Button variant="outline" size="sm" render={<Link href="/login" />}>
          Sign in
        </Button>
      </AlertDescription>
    </Alert>
  )
}
