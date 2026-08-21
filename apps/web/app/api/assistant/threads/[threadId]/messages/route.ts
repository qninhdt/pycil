import { NextResponse } from "next/server"

import { accessTokenForRequest } from "@/lib/api/request"
import { proxyToApi } from "@/lib/api/upstream"
import { getSession } from "@/lib/auth/session"

export async function POST(
  request: Request,
  { params }: { params: Promise<{ threadId: string }> }
): Promise<Response> {
  try {
    const session = await getSession()
    const accessToken = await accessTokenForRequest(session)
    if (!session.isLoggedIn || !accessToken) {
      return NextResponse.json(
        { error: { code: "unauthorized", message: "Unauthorized" } },
        { status: 401 }
      )
    }

    const { threadId } = await params

    // The replay cursor: a reconnecting EventSource presents the id of the last
    // event it saw, and the API resumes the run from that frame rather than
    // restarting it. Absent on a first post, present on every reconnect.
    const lastEventId = request.headers.get("Last-Event-ID")

    return await proxyToApi(
      request,
      `/v1/assistant/threads/${threadId}/messages`,
      {
        stream: true,
        headers: {
          Authorization: `Bearer ${accessToken}`,
          ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
        },
      }
    )
  } catch (err) {
    console.error("Assistant SSE proxy error:", err)
    return NextResponse.json(
      {
        error: {
          code: "internal_error",
          message: "Failed to proxy stream message",
        },
      },
      { status: 500 }
    )
  }
}
