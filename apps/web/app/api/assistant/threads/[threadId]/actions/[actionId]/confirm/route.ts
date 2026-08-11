import { NextResponse } from "next/server";
import { accessTokenForRequest } from "@/lib/api/request";
import { getSession } from "@/lib/auth/session";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ threadId: string; actionId: string }> }
) {
  try {
    const session = await getSession();
    const accessToken = await accessTokenForRequest(session);
    if (!session.isLoggedIn || !accessToken) {
      return NextResponse.json(
        { error: { code: "unauthorized", message: "Unauthorized" } },
        { status: 401 }
      );
    }

    const { threadId, actionId } = await params;
    const body = await request.json();
    const apiUrl = process.env.PYCIL_API_URL || "http://localhost:8000";

    const headers: Record<string, string> = {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    };

    const backendRes = await fetch(
      `${apiUrl}/v1/assistant/threads/${threadId}/actions/${actionId}/confirm`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      }
    );

    if (!backendRes.ok) {
      const errorText = await backendRes.text();
      return new Response(errorText, {
        status: backendRes.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(backendRes.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    console.error("Assistant confirm action proxy error:", err);
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to confirm action" } },
      { status: 500 }
    );
  }
}
