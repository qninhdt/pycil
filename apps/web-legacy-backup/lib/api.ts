/**
 * Server-side fetch wrapper for pycil-core.
 *
 * Routes through Caddy at /api/core/* in prod, or PYCIL_CORE_URL directly
 * from server components. Forwards Auth.js cookie so FastAPI can read it.
 */
import { headers } from "next/headers";

const BASE = process.env.PYCIL_CORE_URL || "http://pycil-core:8000";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`);
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const cookie = (await headers()).get("cookie") ?? "";
  const origin =
    process.env.AUTH_URL ?? `https://${process.env.DOMAIN ?? "localhost"}`;
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      origin,
      cookie,
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
