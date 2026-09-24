"use client"

import { useRouter } from "next/navigation"
import Link from "next/link"
import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"
import { startSession } from "@/lib/actions/study"
import { ArrowRightIcon, CoffeeIcon } from "@/lib/icons"

/**
 * The one place a session is created.
 *
 * Creating a session is a POST, so it cannot happen while a page renders: a reload
 * would silently start a second session, and the first would sit abandoned holding
 * reserved deliveries. So this is an explicit action behind a button, and the session
 * id it returns becomes the URL the loop actually runs at.
 *
 * That is also why the deck and folder views link here rather than straight to the
 * runner. The runner's route is keyed by session id precisely so that refreshing it
 * resumes.
 *
 * The source may be a deck or a folder. A folder session gathers every readable sense
 * beneath it once, so a word reachable through two paths is still one item.
 */
export function StartSessionPanel({
  nodeId,
  nodeName,
  nodeType,
  itemCount,
}: {
  nodeId: string
  /** The deck or folder being studied. */
  nodeName: string
  /** Decides the copy: a folder gathers its whole readable subtree. */
  nodeType: "DECK" | "FOLDER"
  /** Words in scope, which is not the same as words due right now. */
  itemCount: number | null
}) {
  const noun = nodeType === "FOLDER" ? "folder" : "deck"
  const scope = nodeType === "FOLDER" ? "this folder and everything inside it" : "this deck"
  const router = useRouter()
  const [starting, start] = useTransition()
  const [problem, setProblem] = useState<string | null>(null)
  const [nothingDue, setNothingDue] = useState(false)

  function begin() {
    start(async () => {
      setProblem(null)
      const result = await startSession(nodeId)

      if (!result.success) {
        setProblem(classifyErrorCode(result.code).message)
        return
      }

      // The server admitted nothing: everything here is either scheduled for later or
      // already finished. Saying so beats navigating to a session that would open on
      // its own recap with no work in it.
      if (result.data.firstState === "exhausted") {
        setNothingDue(true)
        return
      }

      router.replace(`/study/${result.data.sessionId}`)
    })
  }

  if (nothingDue) {
    return (
      <div className="flex flex-col items-center gap-4 text-center">
        <CoffeeIcon className="size-6 text-muted-foreground" aria-hidden />
        <h1 className="text-2xl tracking-tight">Nothing due right now</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          Every word in {scope} is either scheduled for a later day or already
          finished. Coming back when a review falls due is what makes the schedule work.
        </p>
        <Button render={<Link href={`/library/${nodeId}`} />} variant="outline">
          Back to the {noun}
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 text-center">
      <h1 className="text-2xl tracking-tight">{nodeName}</h1>
      {itemCount != null ? (
        <p className="text-sm text-muted-foreground">
          {itemCount} {itemCount === 1 ? "word" : "words"} in this {noun}. The session
          picks what is due and what is new.
        </p>
      ) : null}

      {problem ? <p className="text-sm text-muted-foreground">{problem}</p> : null}

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button onClick={begin} disabled={starting} size="lg">
          {starting ? <Spinner data-icon="inline-start" /> : null}
          Start studying
          <ArrowRightIcon data-icon="inline-end" />
        </Button>
        <Button render={<Link href={`/library/${nodeId}`} />} variant="outline" size="lg">
          Not now
        </Button>
      </div>
    </div>
  )
}
