/**
 * A failed request, said in words the learner can act on.
 *
 * The message comes from `classifyErrorCode`, which is annotated
 * `Record<ApiErrorCode, …>` — so when the API grows a code, the typecheck fails
 * until an entry is written rather than this surface silently rendering
 * "something went wrong". That is why there is no local map of assistant codes
 * here: a second map would be the thing that drifts.
 *
 * This component is reached with a wire code, from the thread-list read that
 * `assistant-surface` performs. A failed *run* does not arrive here: the AG-UI
 * runtime reports it as an Error on its own callback, which the chat surface
 * renders as text, so a run outcome is not a code this component has to know.
 */

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { classifyErrorCode, isRetryable } from "@/lib/api/error-taxonomy"
import { WarningCircleIcon } from "@/lib/icons"

export function AssistantErrorNotice({
  code,
  onRetry,
}: {
  code: string
  onRetry?: () => void
}) {
  const message = classifyErrorCode(code).message

  // Retry is offered only where it can help. A `quota` or `conflict` refusal is a
  // decision the server already made, and a button that re-provokes it teaches the
  // learner that the product is broken rather than that they hit a limit.
  const retryable = Boolean(onRetry) && isRetryable(code)

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
