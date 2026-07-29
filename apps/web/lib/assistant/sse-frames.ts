/**
 * Parsing the assistant's SSE wire format into typed run events.
 *
 * The event union itself lives in `lib/api/types/assistant.ts`, next to the rest of
 * the wire contract. This module is only the transport half: turning the byte stream
 * into those objects.
 *
 * The frames the API writes are `id: <sequence>\nevent: <type>\ndata: <json>\n\n`,
 * with `: heartbeat\n\n` comment frames every fifteen seconds while the model is
 * thinking. A parser that split on newlines alone would treat a heartbeat as an
 * empty event and a multi-line JSON payload as several frames, so the split is on
 * the blank-line frame boundary and comment lines are dropped.
 */

import type { RunEvent, RunEventType } from "@/lib/api/types"

/**
 * Every event type the API emits, as a runtime check for a frame's `event:` line.
 *
 * A `Record<RunEventType, true>` rather than a `Set`. A `new Set<RunEventType>([…])`
 * type-checks that each *member* is a known event, which is the easy half — it says
 * nothing about whether every event is present, so dropping one compiles clean and
 * silently makes that event unparseable at runtime. Keying a record by the union
 * makes a missing entry a compile error, which is the direction that actually
 * matters when the contract grows.
 */
const KNOWN_EVENTS: Record<RunEventType, true> = {
  user_message: true,
  token: true,
  tool_call: true,
  tool_result: true,
  confirmation_required: true,
  done: true,
  error: true,
}

function isKnownEvent(name: string): name is RunEventType {
  return Object.hasOwn(KNOWN_EVENTS, name)
}

export interface ParsedFrame {
  /** The `id:` line, which is the run's monotonic event sequence. */
  sequence: number
  eventType: RunEventType
  payload: unknown
}

/**
 * Accumulates stream chunks and yields whole frames.
 *
 * Stateful because a chunk boundary lands wherever the network puts it, routinely
 * mid-frame and sometimes mid-UTF-8-character. The decoder is called with
 * `stream: true` for the same reason: decoding each chunk independently would
 * corrupt any multi-byte character split across two of them, which for this product
 * means IPA and accented text arriving as replacement characters.
 */
export class SseFrameReader {
  private buffer = ""
  private readonly decoder = new TextDecoder()

  /** Feeds raw bytes in and returns whatever complete frames they completed. */
  push(chunk: Uint8Array): ParsedFrame[] {
    this.buffer += this.decoder.decode(chunk, { stream: true })
    return this.drain()
  }

  /**
   * Flushes at end of stream.
   *
   * A final frame with no trailing blank line is not malformed: the server closes
   * the response as soon as the run ends, so the terminal `done` or `error` can
   * arrive without its boundary. Dropping it would lose exactly the event that says
   * how the run finished.
   */
  flush(): ParsedFrame[] {
    this.buffer += this.decoder.decode()
    const frames = this.drain()
    const remainder = this.buffer.trim()
    this.buffer = ""
    if (!remainder) return frames

    const parsed = parseFrame(remainder)
    return parsed ? [...frames, parsed] : frames
  }

  private drain(): ParsedFrame[] {
    const frames: ParsedFrame[] = []
    let boundary = this.buffer.indexOf("\n\n")

    while (boundary !== -1) {
      const raw = this.buffer.slice(0, boundary)
      this.buffer = this.buffer.slice(boundary + 2)
      const parsed = parseFrame(raw)
      if (parsed) frames.push(parsed)
      boundary = this.buffer.indexOf("\n\n")
    }

    return frames
  }
}

/**
 * One frame to a typed event, or null.
 *
 * Null covers a heartbeat comment, a frame with an event name this client does not
 * know, and malformed JSON. All three are skipped rather than thrown: the stream is
 * the only path a verdict or an approval request arrives on, and killing it over one
 * unrecognised frame would lose every event after it.
 */
function parseFrame(raw: string): ParsedFrame | null {
  let sequence: number | null = null
  let eventType: string | null = null
  const dataLines: string[] = []

  for (const line of raw.split("\n")) {
    // A comment frame. The API sends these as keep-alives so an idle connection is
    // not closed by an intermediary while the model is still working.
    if (line.startsWith(":")) continue

    if (line.startsWith("id:")) {
      const parsed = Number(line.slice(3).trim())
      if (Number.isInteger(parsed)) sequence = parsed
    } else if (line.startsWith("event:")) {
      eventType = line.slice(6).trim()
    } else if (line.startsWith("data:")) {
      // Joined rather than overwritten: the spec allows a payload to span several
      // `data:` lines, and taking only the last would truncate it.
      dataLines.push(line.slice(5).trimStart())
    }
  }

  if (sequence === null || !eventType || !isKnownEvent(eventType)) return null

  try {
    return {
      // Narrowed by the guard above, so no cast is needed here.
      sequence,
      eventType,
      payload: JSON.parse(dataLines.join("\n")),
    }
  } catch {
    return null
  }
}

/**
 * A parsed frame as a `RunEvent`.
 *
 * `runId` has to be passed in because the wire format is `id: <sequence>` with no
 * run identity, while the same event replayed from `GET .../messages` carries one.
 * Both shapes have to be one type for the transcript to hold them in a single list,
 * and the run id is what keeps this turn's sequence 1 from colliding with the next
 * turn's. The caller passes the turn's `clientMessageId`, which names the same run
 * by its idempotency key.
 *
 * The row id is synthesised from both for the same reason: unique within a run is
 * not unique within a thread.
 */
export function toRunEvent(frame: ParsedFrame, runId: string): RunEvent {
  return {
    id: `${runId}-${frame.sequence}`,
    runId,
    sequence: frame.sequence,
    eventType: frame.eventType,
    // The union is keyed by `eventType` and each payload shape is checked at its
    // use site, so the cast is confined here rather than spread across consumers.
    payload: frame.payload,
  } as RunEvent
}
