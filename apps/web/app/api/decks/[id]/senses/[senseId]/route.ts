import { NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSession } from "@/lib/auth/session";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string; senseId: string }> }
) {
  try {
    const session = await getSession();
    const client = createApiClient(session);
    const { id, senseId } = await params;

    await client.removeSenseFromDeck(id, parseInt(senseId, 10));
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to remove sense from deck" } },
      { status: 500 }
    );
  }
}
