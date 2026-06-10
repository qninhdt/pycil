export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE ?? "/api/core";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

async function fetchJsonMock<T>(path: string, init: RequestInit): Promise<T> {
  // Dynamic import keeps the mock layer out of the real-backend bundle.
  const { handle } = await import("../mock/router");
  const method = (init.method ?? "GET").toUpperCase();
  let body: unknown = undefined;
  if (typeof init.body === "string" && init.body.length > 0) {
    try {
      body = JSON.parse(init.body);
    } catch {
      body = init.body;
    }
  }
  try {
    return handle(method, path, body) as T;
  } catch (err) {
    const status = (err as { __status?: number }).__status ?? 500;
    const message = (err as Error).message || "mock_error";
    throw new ApiError(status, message, message);
  }
}

let unauthorizedHandler: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn;
}

function extractCodeAndMessage(body: unknown, fallback: string) {
  if (typeof body === "string") return { code: fallback, message: body };
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return { code: fallback, message: detail };
    if (detail && typeof detail === "object") {
      const code = (detail as { code?: string }).code ?? fallback;
      const message = (detail as { message?: string }).message ?? code;
      return { code, message };
    }
  }
  return { code: fallback, message: fallback };
}

export async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  if (USE_MOCK) return fetchJsonMock<T>(path, init);

  const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  headers.set("accept", "application/json");

  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers,
  });

  if (res.status === 401) {
    if (unauthorizedHandler) unauthorizedHandler();
    throw new ApiError(401, "unauthorized", "session expired");
  }

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const fallback = res.statusText || "request_failed";
    const { code, message } = extractCodeAndMessage(body, fallback);
    throw new ApiError(res.status, code, message, body);
  }

  return body as T;
}

export function streamUrl(path: string): string {
  return path.startsWith("http") ? path : `${BASE_URL}${path}`;
}
