"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import { PaperPlaneRightIcon } from "@/lib/icons"

/**
 * The API's own limit, from `settings.assistant_max_message_chars`.
 *
 * Enforced here because the server answers an over-length message with a **413**
 * (`assistant_message_too_long`). A rejected request mid-conversation still
 * breaks the send flow, when the real cause is a message the learner can simply
 * shorten. Refusing locally turns a failed send into a visible character count.
 */
const MAX_CHARS = 8000

/**
 * Where a turn is written.
 *
 * Submission is blocked while a run is open rather than queued. The API allows one
 * active run per thread and answers a second with `assistant_thread_run_active`, so
 * a queue here would only be a place for messages to fail later.
 */
export function AssistantComposer({
  disabled,
  disabledReason,
  onSend,
}: {
  disabled: boolean
  /** Shown instead of the hint, so a blocked composer says why. */
  disabledReason?: string
  onSend: (content: string) => void
}) {
  const [draft, setDraft] = useState("")

  const trimmed = draft.trim()
  const tooLong = draft.length > MAX_CHARS
  const canSend = trimmed.length > 0 && !tooLong && !disabled

  function submit() {
    if (!canSend) return
    onSend(trimmed)
    setDraft("")
  }

  return (
    <div className="flex flex-col gap-1.5">
      <InputGroup>
        <InputGroupTextarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          // Enter sends, Shift+Enter breaks the line. The composer is a chat input,
          // not a document, so the common case is the shorter keystroke.
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder={disabled ? "" : "Ask about your library"}
          aria-label="Message the assistant"
          aria-invalid={tooLong || undefined}
          disabled={disabled}
          rows={2}
        />
        <InputGroupAddon align="block-end">
          {/* The count appears only as it starts to matter. Showing "0 / 8000"
              against an empty box implies a limit the learner will never reach. */}
          {draft.length > MAX_CHARS * 0.8 ? (
            <span
              className={
                tooLong ? "text-xs text-destructive" : "text-xs text-muted-foreground"
              }
            >
              {draft.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
            </span>
          ) : null}
          <Button
            size="icon-sm"
            aria-label="Send"
            className="ml-auto"
            disabled={!canSend}
            onClick={submit}
          >
            <PaperPlaneRightIcon />
          </Button>
        </InputGroupAddon>
      </InputGroup>

      {tooLong ? (
        <p className="text-xs text-destructive">
          That is {(draft.length - MAX_CHARS).toLocaleString()} characters over the
          limit. Shorten it to send.
        </p>
      ) : disabledReason ? (
        <p className="text-xs text-muted-foreground">{disabledReason}</p>
      ) : null}
    </div>
  )
}
