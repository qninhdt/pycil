"use client"

import { useEffect } from "react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { WarningCircleIcon } from "@/lib/icons"

/**
 * The boundary for the study screen.
 *
 * The study route sits outside the shell group on purpose, so `(app)/error.tsx` does
 * not cover it and without this file a failed read would fall through to the global
 * boundary, which replaces the whole document. This keeps the failure inside the
 * study frame and offers the two ways out that make sense here.
 *
 * A retry is safe. Everything this route reads on the server is a true read: the
 * session endpoint advances nothing and reserves nothing, unlike `/next`, which is
 * never called during render.
 */
export default function StudyError({
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
    <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-5 px-4 text-center">
      <WarningCircleIcon className="size-6 text-muted-foreground" aria-hidden />

      <div className="flex max-w-sm flex-col gap-2">
        <h1 className="text-xl tracking-tight">This session could not be loaded</h1>
        <p className="text-sm text-muted-foreground">
          Answers you have already given are recorded, so nothing is lost by trying
          again or coming back to this deck later.
        </p>
        {error.digest ? (
          <p className="font-mono text-xs text-muted-foreground">
            Reference: {error.digest}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button onClick={reset}>Try again</Button>
        <Button render={<Link href="/library" />} variant="outline">
          Back to library
        </Button>
      </div>
    </div>
  )
}
