// Mock request router. Maps (method, path) → handler, mirroring the FastAPI
// routes that api-client/* calls. Returns schema-faithful payloads.
// Dispatched from fetchJson when NEXT_PUBLIC_USE_MOCK==="true".

import { matchRoute } from "./match";
import * as nodes from "./handlers/nodes";
import * as terms from "./handlers/terms";
import * as questions from "./handlers/questions";
import * as learning from "./handlers/learning";
import * as me from "./handlers/me";

export type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE" | "PUT";

interface Route {
  method: HttpMethod;
  pattern: string;
  handle: (
    params: Record<string, string>,
    body: unknown,
    query: URLSearchParams,
  ) => unknown;
}

function num(v: string): number {
  const n = Number(v);
  if (Number.isNaN(n)) throw status(400, "invalid_id");
  return n;
}

function status(code: number, message: string): Error {
  return Object.assign(new Error(message), { __status: code });
}

// Order matters: more specific patterns first.
const ROUTES: Route[] = [
  // --- me / onboarding ---
  { method: "GET", pattern: "/me", handle: () => me.getMe() },
  { method: "PATCH", pattern: "/me", handle: (_p, body) => me.updateMe(body as Parameters<typeof me.updateMe>[0]) },
  { method: "POST", pattern: "/onboarding/seed", handle: () => me.seedOnboarding() },

  // --- nodes ---
  { method: "GET", pattern: "/nodes/root", handle: () => nodes.listRootNodes() },
  { method: "POST", pattern: "/nodes", handle: (_p, body) => nodes.createNode(body as Parameters<typeof nodes.createNode>[0]) },
  { method: "GET", pattern: "/nodes/:id/children", handle: (p) => nodes.listNodeChildren(p.id) },
  { method: "POST", pattern: "/nodes/:id/star", handle: (p) => nodes.toggleStar(p.id) },
  { method: "POST", pattern: "/nodes/:id/pin", handle: (p) => nodes.togglePin(p.id) },
  { method: "GET", pattern: "/nodes/:id", handle: (p) => nodes.getNode(p.id) },
  { method: "PATCH", pattern: "/nodes/:id", handle: (p, body) => nodes.updateNode(p.id, body as Parameters<typeof nodes.updateNode>[1]) },
  { method: "DELETE", pattern: "/nodes/:id", handle: (p) => { nodes.deleteNode(p.id); return undefined; } },

  // --- terms ---
  { method: "GET", pattern: "/decks/:id/terms", handle: (p) => terms.listDeckTerms(p.id) },
  { method: "POST", pattern: "/decks/:id/terms", handle: (p, body) => terms.addTerm(p.id, (body as { value: string }).value) },

  // --- learning sessions ---
  { method: "POST", pattern: "/decks/:id/sessions", handle: (p, body) => learning.startSession(p.id, (body as { session_size?: number } | undefined)?.session_size) },
  { method: "GET", pattern: "/sessions/:id/question", handle: (p) => learning.getSessionQuestion(p.id) },
  { method: "POST", pattern: "/sessions/:id/answer", handle: (p, body) => { const b = body as { question_id: string; selected_index: number }; return learning.submitAnswer(p.id, b.question_id, b.selected_index); } },

  // --- questions ---
  { method: "GET", pattern: "/definitions/:id/question", handle: (p) => questions.fetchOrEnqueueQuestion(num(p.id)) },
  { method: "POST", pattern: "/questions/:id/check", handle: (p, body) => questions.checkAnswer(p.id, (body as { selected_index: number }).selected_index) },
];

export function handle(
  method: string,
  path: string,
  body?: unknown,
): unknown {
  const m = method.toUpperCase() as HttpMethod;
  for (const route of ROUTES) {
    if (route.method !== m) continue;
    const match = matchRoute(route.pattern, path);
    if (match) return route.handle(match.params, body, match.query);
  }
  throw status(404, "not_found");
}
