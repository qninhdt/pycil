import { NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSession } from "@/lib/auth/session";

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const session = await getSession();
    const client = createApiClient(session);
    const { id } = await params;
    const body = await request.json();

    const data = await client.moveNode(id, body);
    return NextResponse.json(data);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to move node" } },
      { status: 500 }
    );
  }
}
