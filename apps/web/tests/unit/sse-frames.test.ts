import { describe, expect, it } from "vitest"

import { SseFrameReader, toRunEvent } from "@/lib/assistant/sse-frames"

/** The wire encoder used by every case, mirroring the API's frame shape. */
function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

function frame(sequence: number, event: string, data: unknown): string {
  return `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

describe("SseFrameReader", () => {
  it("parses one whole frame", () => {
    const reader = new SseFrameReader()
    const frames = reader.push(encode(frame(1, "token", { content: "hi" })))

    expect(frames).toEqual([
      { sequence: 1, eventType: "token", payload: { content: "hi" } },
    ])
  })

  it("reassembles a frame split across chunk boundaries", () => {
    const reader = new SseFrameReader()
    const whole = frame(3, "token", { content: "split" })
    const cut = Math.floor(whole.length / 2)

    // The network puts the boundary wherever it likes, routinely mid-frame.
    expect(reader.push(encode(whole.slice(0, cut)))).toEqual([])
    const frames = reader.push(encode(whole.slice(cut)))

    expect(frames).toEqual([
      { sequence: 3, eventType: "token", payload: { content: "split" } },
    ])
  })

  it("keeps a multi-byte character whole when the split lands mid-codepoint", () => {
    // "ɪ" (U+026A, IPA) is two UTF-8 bytes. A decoder called per-chunk without
    // `stream: true` would turn a byte split here into replacement characters —
    // exactly the IPA-mangling this product cannot ship.
    const reader = new SseFrameReader()
    const bytes = encode(frame(1, "token", { content: "ɪ" }))
    const mid = bytes.indexOf(0xc9) + 1 // between the two bytes of ɪ

    reader.push(bytes.slice(0, mid))
    const frames = reader.push(bytes.slice(mid))

    expect(frames.at(-1)?.payload).toEqual({ content: "ɪ" })
  })

  it("drops heartbeat comment frames without emitting an event", () => {
    const reader = new SseFrameReader()
    const frames = reader.push(encode(": heartbeat\n\n" + frame(2, "done", {})))

    expect(frames).toEqual([{ sequence: 2, eventType: "done", payload: {} }])
  })

  it("skips an unknown event name rather than throwing", () => {
    // A newer API can invent an event this build has never heard of. Killing the
    // stream over it would lose every event after it, so it is dropped instead.
    const reader = new SseFrameReader()
    const frames = reader.push(
      encode(frame(1, "some_future_event", {}) + frame(2, "done", {})),
    )

    expect(frames).toEqual([{ sequence: 2, eventType: "done", payload: {} }])
  })

  it("skips a frame with malformed JSON rather than throwing", () => {
    const reader = new SseFrameReader()
    const frames = reader.push(
      encode("id: 1\nevent: token\ndata: {not json\n\n" + frame(2, "done", {})),
    )

    expect(frames).toEqual([{ sequence: 2, eventType: "done", payload: {} }])
  })

  it("emits a terminal frame that arrives without its trailing blank line", () => {
    // The server closes the response the instant the run ends, so `done` can land
    // with no boundary. `flush` at end of stream must not drop it.
    const reader = new SseFrameReader()
    reader.push(encode(frame(1, "token", { content: "hi" })))
    const tail = reader.push(encode("id: 2\nevent: done\ndata: {}"))
    expect(tail).toEqual([])

    expect(reader.flush()).toEqual([
      { sequence: 2, eventType: "done", payload: {} },
    ])
  })

  it("joins a payload spanning several data: lines", () => {
    const reader = new SseFrameReader()
    const frames = reader.push(
      encode('id: 1\nevent: token\ndata: {"content":\ndata: "wrapped"}\n\n'),
    )

    expect(frames).toEqual([
      { sequence: 1, eventType: "token", payload: { content: "wrapped" } },
    ])
  })
})

describe("toRunEvent", () => {
  it("stamps the run id the wire format omits and synthesises a per-run id", () => {
    const event = toRunEvent(
      { sequence: 4, eventType: "token", payload: { content: "x" } },
      "run-abc",
    )

    expect(event.runId).toBe("run-abc")
    // Unique within a run is not unique within a thread, so the row id carries both.
    expect(event.id).toBe("run-abc-4")
    expect(event.sequence).toBe(4)
  })
})
