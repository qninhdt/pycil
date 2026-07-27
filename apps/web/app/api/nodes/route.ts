import { NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSession } from "@/lib/auth/session";

export async function GET(request: Request) {
  try {
    const session = await getSession();
    const client = createApiClient(session);
    const { searchParams } = new URL(request.url);

    const parentNodeId = searchParams.get("parentNodeId");
    const cursor = searchParams.get("cursor") || undefined;
    const limitParam = searchParams.get("limit");
    const limit = limitParam ? parseInt(limitParam, 10) : 50;

    const data = await client.getNodes(parentNodeId, cursor, limit);
    return NextResponse.json(data);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to fetch nodes" } },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  try {
    const session = await getSession();
    const client = createApiClient(session);
    const body = await request.json();

    const data = await client.createNode(body);
    return NextResponse.json(data, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: { code: err.code, message: err.message } },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: { code: "internal_error", message: "Failed to create node" } },
      { status: 500 }
    );
  }
}
