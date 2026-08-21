import { NextResponse } from "next/server"

import { accessTokenForRequest } from "@/lib/api/request"
import { proxyToApi } from "@/lib/api/upstream"
import { getSession } from "@/lib/auth/session"

export async function POST(
  request: Request,
  { params }: { params: Promise<{ threadId: string; actionId: string }> }
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

    const { threadId, actionId } = await params

    // No replay cursor here on purpose: a decision continues an open run, so
    // there is no earlier stream to resume. The per-route difference from the
    // messages proxy is exactly this header and nothing else.
    return await proxyToApi(
      request,
      `/v1/assistant/threads/${threadId}/actions/${actionId}/confirm`,
      {
        stream: true,
        headers: { Authorization: `Bearer ${accessToken}` },
      }
    )
  } catch (err) {
    console.error("Assistant confirm action proxy error:", err)
    return NextResponse.json(
      {
        error: {
          code: "internal_error",
          message: "Failed to confirm action",
        },
      },
      { status: 500 }
    )
  }
}
