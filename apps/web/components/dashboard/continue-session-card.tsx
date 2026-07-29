"use client"

import Link from "next/link"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyTitle } from "@/components/ui/empty"
import { PlayIcon } from "@/lib/icons"
import type { RecentSession } from "@/lib/api/types"

/**
 * The one action Today exists to offer.
 *
 * `recentSession` is the last deck reviewed, or the learner's first deck if they
 * have never reviewed anything — so this is "where to pick up", not "a session
 * that is still open". It links to the deck, which is where a session is
 * started, rather than to a session id that does not exist yet.
 */
export function ContinueSessionCard({
  recentSession,
  dueCount,
}: {
  recentSession: RecentSession | null
  dueCount: number
}) {
  if (!recentSession) {
    return (
      <Empty>
        <EmptyTitle>No decks yet</EmptyTitle>
        <EmptyDescription>
          Make a deck in your library, then add words to it with search.
        </EmptyDescription>
        <Button render={<Link href="/library" />} className="mt-2">
          Open library
        </Button>
      </Empty>
    )
  }

  return (
    <Card className="card-hover">
      <CardHeader>
        <CardTitle>{recentSession.deckTitle}</CardTitle>
        <CardDescription>
          {dueCount === 0
            ? "Nothing due here right now. You can still study ahead."
            : `${dueCount} ${dueCount === 1 ? "word" : "words"} waiting.`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button render={<Link href={`/library/${recentSession.nodeId}`} />}>
          <PlayIcon data-icon="inline-start" />
          {dueCount === 0 ? "Open deck" : "Start studying"}
        </Button>
      </CardContent>
    </Card>
  )
}
