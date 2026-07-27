"use client"

import { useEffect } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { WarningCircleIcon } from "@/lib/icons"

/**
 * The boundary for every screen inside the shell. The shell itself stays
 * rendered, so navigation still works and the learner is not stranded on a
 * full-page error for one failed read.
 *
 * `error.message` is deliberately not shown. A server-side error is redacted to
 * a generic string in production anyway, so printing it either says nothing or
 * leaks an internal detail; the digest is what makes a report actionable.
 */
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <Alert variant="destructive">
      <WarningCircleIcon />
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription className="flex flex-col items-start gap-3">
        <span>
          This screen could not load. Trying again often works; if it does not,
          the connection to the server is likely down.
        </span>
        {error.digest ? (
          <span className="font-mono text-xs">Reference: {error.digest}</span>
        ) : null}
        <Button variant="outline" size="sm" onClick={reset}>
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  )
}
