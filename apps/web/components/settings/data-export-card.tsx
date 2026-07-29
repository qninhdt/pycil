"use client"

import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { exportAccount } from "@/lib/actions/account"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"

/**
 * Downloading everything the account holds.
 *
 * The payload is written to a file rather than rendered on the page. It carries every
 * node, every review row and the whole assistant history, so putting it inline would
 * lock the tab on a large account and give the learner no way to keep it.
 *
 * The object URL is revoked immediately after the click: without that, the whole export
 * stays in memory for as long as the tab is open, which for the one thing on this screen
 * guaranteed to be large is the wrong default.
 */
export function DataExportCard() {
  const [problem, setProblem] = useState<string | null>(null)
  const [isExporting, startExporting] = useTransition()

  function download() {
    setProblem(null)

    startExporting(async () => {
      const result = await exportAccount()

      if (!result.success) {
        setProblem(classifyErrorCode(result.code).message)
        return
      }

      const blob = new Blob([JSON.stringify(result.data, null, 2)], {
        type: "application/json",
      })
      const url = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.download = `pycil-export-${new Date().toISOString().slice(0, 10)}.json`
      link.click()
      URL.revokeObjectURL(url)
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your data</CardTitle>
        <CardDescription>
          A copy of everything this account holds: your decks, every review you have
          recorded, and your assistant history.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          The file is JSON, and it can be large on an account with a long history.
        </p>
        {problem ? (
          <p className="mt-2 text-sm text-muted-foreground">{problem}</p>
        ) : null}
      </CardContent>
      <CardFooter>
        <Button onClick={download} disabled={isExporting} variant="outline" size="sm">
          {isExporting ? <Spinner data-icon="inline-start" /> : null}
          Download export
        </Button>
      </CardFooter>
    </Card>
  )
}
