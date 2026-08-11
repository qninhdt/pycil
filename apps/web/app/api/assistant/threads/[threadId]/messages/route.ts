import { NextResponse } from "next/server"
import { getSession } from "@/lib/auth/session"
import { accessTokenForRequest } from "@/lib/api/request"

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
    const body = await request.json()
    const apiUrl = process.env.PYCIL_API_URL || "http://localhost:8000"

    const headers: Record<string, string> = {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    }

    const lastEventId = request.headers.get("Last-Event-ID")
    if (lastEventId) {
      headers["Last-Event-ID"] = lastEventId
    }

    const backendRes = await fetch(
      `${apiUrl}/v1/assistant/threads/${threadId}/messages`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      }
    )

    if (!backendRes.ok) {
      const errorText = await backendRes.text()
      return new Response(errorText, {
        status: backendRes.status,
        headers: { "Content-Type": "application/json" },
      })
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
