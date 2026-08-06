/**
 * A failed request, said in words the learner can act on.
 *
 * The message comes from `classifyErrorCode`, which is annotated
 * `Record<ApiErrorCode, …>` — so when the API grows a code, the typecheck fails
 * until an entry is written rather than this surface silently rendering
 * "something went wrong". That is why there is no local map of assistant codes
 * here: a second map would be the thing that drifts.
 *
 * The codes below are the ones that map cannot cover, for two different reasons.
 * `stream_failed` and `not_authenticated` never came from the API at all — one is
 * a dropped connection, the other this app declining to send a request.
 *
 * `deadline_exceeded` and `execution_failed` are subtler: they *are* the API's, but
 * they are written into an `error` event's payload rather than raised as HTTP
 * errors, so the code generator that reads the error classes never sees them and
 * `classifyErrorCode` returns its generic fallback. Without them here, a run that
 * timed out and a run that crashed both read as "something went wrong" — which
 * hides the one distinction that tells the learner whether waiting will help.
 */

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { classifyErrorCode, isRetryable } from "@/lib/api/error-taxonomy"
import { WarningCircleIcon } from "@/lib/icons"

/** Codes the generated wire taxonomy cannot reach. See the note above. */
const LOCAL_MESSAGES: Record<string, string> = {
  stream_failed: "The connection dropped before the reply finished.",
  not_authenticated: "Sign in to use the assistant.",
  // Run outcomes, from an `error` event payload rather than an HTTP response.
  deadline_exceeded: "The assistant ran out of time on that one. Try a smaller ask.",
  execution_failed: "The assistant hit an error partway through and stopped.",
}

/**
 * Which of those are worth retrying.
 *
 * A timeout may pass on a smaller request, and a dropped stream is transport. A
 * crashed run is not: the same request will crash the same way, so offering a retry
 * would just spend the learner's time proving it.
 */
const LOCAL_RETRYABLE: ReadonlySet<string> = new Set([
  "stream_failed",
  "deadline_exceeded",
])

export function AssistantErrorNotice({
  code,
  onRetry,
}: {
  code: string
  onRetry?: () => void
}) {
  const local = LOCAL_MESSAGES[code]
  const message = local ?? classifyErrorCode(code).message

  // Retry is offered only where it can help. A `quota` or `conflict` refusal is a
  // decision the server already made, and a button that re-provokes it teaches the
  // learner that the product is broken rather than that they hit a limit. Local
  // codes are judged by their own set rather than by being local: `execution_failed`
  // is local and emphatically not retryable.
  const retryable =
    Boolean(onRetry) && (local ? LOCAL_RETRYABLE.has(code) : isRetryable(code))

  return (
    <Alert variant="destructive">
      <WarningCircleIcon />
      <AlertTitle>The assistant could not continue</AlertTitle>
      <AlertDescription>
        {message}
        {retryable ? (
          <Button variant="outline" size="sm" onClick={onRetry} className="mt-2 w-fit">
            Try again
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  )
}
