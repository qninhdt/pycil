/**
 * The minimal shape this module reads.
 *
 * Structural rather than imported from `@ag-ui/core`, which is not a direct
 * dependency here: the live stream and a persisted thread read disagree on where
 * the request sits, and both arrive as plain JSON, so a structural type is what
 * actually describes the input.
 */
export interface InterruptLike {
  id: string
  toolCallId?: string | null
  action_requests?: unknown
  targets?: unknown
  tool?: unknown
  metadata?: unknown
}

/**
 * The approval a pending interrupt is asking about.
 *
 * Two sources produce this: a live stream, where the adapter nests the
 * HumanInTheLoop request under `metadata.langgraph.raw`, and a persisted thread
 * read, where the request is already at the top level. Both are normalized here so
 * the card never has to know which one it got — reading only one shape is how the
 * card ends up showing "an action" for a delete.
 */
export interface ApprovalAction {
  tool: string
  targets: Record<string, string>
  /** The originating tool call, when the interrupt carried one. */
  toolCallId: string | null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function stringTargets(value: unknown): Record<string, string> {
  const record = asRecord(value)
  if (!record) return {}
  return Object.fromEntries(
    Object.entries(record).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  )
}

/** The tool call an interrupt is asking about, from whichever shape carried it. */
function actionRequest(interrupt: InterruptLike): Record<string, unknown> | null {
  const direct = asRecord(interrupt)
  const requests = direct?.action_requests
  if (Array.isArray(requests)) {
    const first = asRecord(requests[0])
    if (first) return first
  }
  // A live stream puts the request under the adapter's own metadata envelope,
  // because the AG-UI interrupt fields do not carry action_requests.
  const metadata = asRecord(direct?.metadata)
  const raw = asRecord(asRecord(metadata?.langgraph)?.raw)
  const rawRequests = raw?.action_requests
  if (Array.isArray(rawRequests)) return asRecord(rawRequests[0])
  return null
}

export function approvalAction(interrupt: InterruptLike): ApprovalAction {
  const request = actionRequest(interrupt)
  const direct = asRecord(interrupt)
  const toolCallId = request?.toolCallId ?? direct?.toolCallId
  return {
    tool: String(request?.name ?? direct?.tool ?? "action"),
    targets: stringTargets(request?.args ?? direct?.targets),
    toolCallId: typeof toolCallId === "string" && toolCallId ? toolCallId : null,
  }
}