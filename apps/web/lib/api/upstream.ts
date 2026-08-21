import "server-only"

/**
 * The seam between this app's route handlers and the Pycil API.
 *
 * Route handlers under `app/api` exist only where the browser must be an HTTP
 * peer of the API — the OAuth redirects and the assistant SSE proxy. Every one
 * of them needs the same two things: where the API lives, and how a browser
 * request is forwarded to it. Both are defined here, once, so a route handler
 * reduces to its own preamble (auth, redirects, cookies) plus a call.
 */

/** Root URL of the Pycil API, defaulting to the compose stack's local port. */
export function apiUrl(): string {
  return process.env.PYCIL_API_URL || "http://localhost:8000"
}

export interface ProxyOptions {
  /**
   * Headers sent upstream on top of the JSON defaults.
   *
   * This is deliberately where per-route differences stay visible: the messages
   * proxy forwards `Last-Event-ID` so a reconnecting stream resumes its run
   * instead of restarting it, while the confirm proxy has nothing to replay.
   */
  headers?: Record<string, string>
  /**
   * Answer with the server-sent-event framing the assistant contract expects.
   *
   * Defaults to true because both current proxies carry streams; a plain JSON
   * passthrough can opt out explicitly.
   */
  stream?: boolean
}

/**
 * Forwards a route-handler request to the API and builds the browser's response.
 *
 * The response body is handed over unread. Byte-faithful passthrough is what
 * keeps event boundaries intact, and intact boundaries are what make
 * `Last-Event-ID` replay pick up at the right frame after a dropped connection.
 */
export async function proxyToApi(
  request: Request,
  path: string,
  options: ProxyOptions = {}
): Promise<Response> {
  const backendRes = await fetch(`${apiUrl()}${path}`, {
    method: request.method,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    // Reparsed rather than piped raw: every proxied endpoint takes JSON, and a
    // malformed body should keep failing here as it always has, in this app's
    // own error envelope, rather than as whatever the upstream validator makes
    // of it.
    body: JSON.stringify(await request.json()),
  })

  if (!backendRes.ok) {
    const errorText = await backendRes.text()
    return new Response(errorText, {
      status: backendRes.status,
      headers: { "Content-Type": "application/json" },
    })
  }

  if (!options.stream) {
    return new Response(backendRes.body, { status: backendRes.status })
  }

  return new Response(backendRes.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  })
}
