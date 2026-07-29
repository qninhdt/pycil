"use client"

import { Button } from "@/components/ui/button"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { WarningCircleIcon } from "@/lib/icons"

/**
 * What to say when a stream ended without the run ending.
 *
 * This is the honest version of "resume". The API cannot resume an interrupted run:
 * `GET .../messages` and the run query endpoint both replay *persisted* rows and then
 * close, and nothing reattaches to the live generator. Worse, a mid-stream disconnect
 * raises `GeneratorExit` inside `stream_run`, which is a `BaseException` and so escapes
 * its `except Exception` handlers — the run stays `RUNNING` with its work abandoned and
 * no terminal event will ever be written.
 *
 * So there are exactly two truthful offers: re-read what the server persisted, or send
 * the turn again as a new run. Claiming the original reply is still coming would be a
 * lie the transport cannot make good on.
 */
export function RunRecoveryNotice({
  onReplay,
  onResend,
  busy,
}: {
  /** Re-reads the run's persisted events. Absent when no run id is known yet. */
  onReplay?: () => void
  /** Discards the turn key so the next message starts a fresh run. */
  onResend: () => void
  busy: boolean
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3">
      <Marker>
        <MarkerIcon>
          <WarningCircleIcon />
        </MarkerIcon>
        <MarkerContent>
          The connection dropped before this reply finished. It will not carry on by
          itself.
        </MarkerContent>
      </Marker>

      <div className="flex flex-wrap gap-2">
        {onReplay ? (
          <Button variant="outline" size="sm" onClick={onReplay} disabled={busy}>
            Check for more
          </Button>
        ) : null}
        <Button size="sm" onClick={onResend} disabled={busy}>
          Send again
        </Button>
      </div>
    </div>
  )
}
