import { notFound } from "next/navigation"

import { QuestionStage } from "@/components/study/question-stage"
import { StartSessionPanel } from "@/components/study/start-session-panel"
import { readNode } from "@/lib/actions/library-reads"

/**
 * The launch screen for a session on one node.
 *
 * This route exists because the runner is keyed by session id, not node id: refreshing
 * the runner must resume the same session, which only works if the id is already in the
 * URL. Something has to create the session and put it there, and it cannot be a render
 * — creating one is a POST, and a reload would start a second session while the first
 * kept its reserved deliveries.
 *
 * So the page only reads the node and states what is about to happen. The POST is
 * behind the button, and its response decides where the learner goes next.
 */
export default async function StartStudyPage({
  params,
}: {
  params: Promise<{ nodeId: string }>
}) {
  const { nodeId } = await params

  const node = await readNode(nodeId)

  // Absent, private to someone else, or deleted all arrive as one 404 from the API, and
  // one not-found page here, which is what stops this route being used to probe ids.
  if (!node) notFound()

  return (
    <QuestionStage>
      <StartSessionPanel
        nodeId={nodeId}
        deckTitle={node.name}
        itemCount={node.itemCount ?? null}
      />
    </QuestionStage>
  )
}
