import { notFound } from "next/navigation"

import { SessionRunner } from "@/components/study/session-runner"
import { readNode } from "@/lib/actions/library-reads"
import { readSession } from "@/lib/actions/study"

/**
 * One study session, addressed by its own id.
 *
 * The id is in the URL rather than the deck's, so a reload resumes this session
 * instead of starting a second one. Creating a session is a POST that belongs to the
 * launch screen; rendering a page must never have that side effect.
 *
 * The first read here is the true session read, not `/next`. `/next` advances the
 * round and reserves a delivery, so calling it during render would consume a question
 * on every refresh. This endpoint advances nothing, and it answers for a finished
 * session too — from the durable summary, which is what lets the recap survive a
 * reload after the live state has been deleted.
 */
export default async function StudySessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>
}) {
  const { sessionId } = await params

  const session = await readSession(sessionId)

  // An unknown id and someone else's session are the same 404 by design, so that the
  // endpoint cannot be used to discover which sessions exist.
  if (!session.success) notFound()

  // The deck name is for the live-session notice the palette and deck views read, so a
  // failed lookup costs a label rather than the session.
  const node = session.data.nodeId ? await readNode(session.data.nodeId) : null

  return (
    <SessionRunner
      sessionId={sessionId}
      initialSession={session.data}
      deckTitle={node?.name ?? "this deck"}
    />
  )
}
