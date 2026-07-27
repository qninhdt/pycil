import "server-only";

import type { SessionData } from "@/lib/auth/types";

import { ApiError, ApiErrorEnvelope } from "./errors";
import type {
  AccountExport,
  AssistantRunEvent,
  AssistantThread,
  Capabilities,
  CefrDistribution,
  DashboardStatsRead,
  DeckSettingsRead,
  DeckSettingsUpdate,
  FolderItemRead,
  FolderStats,
  GenerationCreateRead,
  GradeResponse,
  HistoryBucketRead,
  NextQuestionResponse,
  NodeCreateRequest,
  NodeItem,
  NodeMoveRequest,
  NodePageResponse,
  NodeUpdateRequest,
  NodeVisibilityRequest,
  RealtimeToken,
  SenseAddResponse,
  SenseItem,
  SessionStartResponse,
  User,
  WeakSenseRead,
  WordSearchRead,
} from "./types";

function isObject(val: unknown): val is Record<string, unknown> {
  return val !== null && typeof val === "object" && !Array.isArray(val);
}

function snakeToCamel(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

export function toCamelCase<T>(obj: unknown): T {
  if (Array.isArray(obj)) {
    return obj.map((item) => toCamelCase(item)) as unknown as T;
  }
  if (isObject(obj)) {
    const n: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      n[snakeToCamel(key)] = toCamelCase(value);
    }
    return n as T;
  }
  return obj as T;
}

export function createApiClient(session: SessionData) {
  const apiUrl = process.env.PYCIL_API_URL || "http://localhost:8000";

  async function ensureValidAccessToken(): Promise<string | undefined> {
    if (!session.accessToken) return undefined;

    const now = Math.floor(Date.now() / 1000);
    const expiresAt = session.expiresAt || 0;

    // Refresh if within 60 seconds of expiry
    if (expiresAt - now < 60 && session.refreshToken) {
      try {
        const refreshRes = await fetch(`${apiUrl}/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: session.refreshToken }),
          cache: "no-store",
        });

        if (refreshRes.ok) {
          const data = await refreshRes.json();
          session.accessToken = data.access_token;
          session.refreshToken = data.refresh_token;
          session.expiresAt = now + data.expires_in;
          session.refreshExpiresAt = now + data.refresh_expires_in;
        }
      } catch (err) {
        console.warn("Failed transparent token refresh in API client:", err);
      }
    }

    return session.accessToken;
  }

  async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await ensureValidAccessToken();
    const headers = new Headers(options.headers || {});

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(`${apiUrl}${path}`, {
      ...options,
      headers,
      cache: "no-store",
    });

    if (response.status === 204) {
      return undefined as T;
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    if (!response.ok) {
      if (isObject(body) && "error" in body) {
        const env = body as unknown as ApiErrorEnvelope;
        throw new ApiError(
          env.error.code,
          env.error.message,
          response.status,
          env.error.requestId,
          env.error.details
        );
      }
      throw new ApiError(
        "http_error",
        `API request failed with status ${response.status}`,
        response.status
      );
    }

    return toCamelCase<T>(body);
  }

  return {
    getMe: () => apiFetch<User>("/v1/me"),
    getCapabilities: () => apiFetch<Capabilities>("/v1/capabilities"),
    getRealtimeToken: () => apiFetch<RealtimeToken>("/v1/realtime/token"),

    // Nodes
    getNodes: (parentNodeId?: string | null, cursor?: string, limit = 50) => {
      const params = new URLSearchParams();
      if (parentNodeId) params.set("parentNodeId", parentNodeId);
      if (cursor) params.set("cursor", cursor);
      params.set("limit", limit.toString());
      const query = params.toString();
      return apiFetch<NodePageResponse>(`/v1/nodes${query ? `?${query}` : ""}`);
    },

    createNode: (data: NodeCreateRequest) =>
      apiFetch<NodeItem>("/v1/nodes", {
        method: "POST",
        body: JSON.stringify({
          type: data.type,
          name: data.name,
          parentNodeId: data.parentNodeId,
          targetNodeId: data.targetNodeId,
          description: data.description,
          visibility: data.visibility,
          confirmSubtreePublication: data.confirmSubtreePublication,
        }),
      }),

    getNode: (id: string) => apiFetch<NodeItem>(`/v1/nodes/${id}`),

    updateNode: (id: string, data: NodeUpdateRequest) =>
      apiFetch<NodeItem>(`/v1/nodes/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    moveNode: (id: string, data: NodeMoveRequest) =>
      apiFetch<NodeItem>(`/v1/nodes/${id}/move`, {
        method: "PATCH",
        body: JSON.stringify({ parentNodeId: data.parentNodeId }),
      }),

    updateNodeVisibility: (id: string, data: NodeVisibilityRequest) =>
      apiFetch<NodeItem>(`/v1/nodes/${id}/visibility`, {
        method: "PATCH",
        body: JSON.stringify({
          visibility: data.visibility,
          confirmSubtreePublication: data.confirmSubtreePublication,
        }),
      }),

    deleteNode: (id: string) =>
      apiFetch<void>(`/v1/nodes/${id}`, {
        method: "DELETE",
      }),

    // Decks & Senses
    getDeckItems: (nodeId: string) => apiFetch<SenseItem[]>(`/v1/decks/${nodeId}/items`),

    updateDeckSettings: (nodeId: string, data: DeckSettingsUpdate) =>
      apiFetch<DeckSettingsRead>(`/v1/decks/${nodeId}/settings`, {
        method: "PATCH",
        body: JSON.stringify({
          new_per_batch: data.newPerBatch,
          review_per_batch: data.reviewPerBatch,
        }),
      }),

    addSenseToDeck: (nodeId: string, senseId: number) =>
      apiFetch<SenseAddResponse>(`/v1/decks/${nodeId}/senses`, {
        method: "POST",
        body: JSON.stringify({ senseId }),
      }),

    removeSenseFromDeck: (nodeId: string, senseId: number) =>
      apiFetch<void>(`/v1/decks/${nodeId}/senses/${senseId}`, {
        method: "DELETE",
      }),

    // Folder Subtree & Analytics
    getFolderItems: (nodeId: string, offset = 0, limit = 50) =>
      apiFetch<FolderItemRead[]>(`/v1/folders/${nodeId}/items?offset=${offset}&limit=${limit}`),

    getFolderWeakest: (nodeId: string, limit = 10) =>
      apiFetch<WeakSenseRead[]>(`/v1/folders/${nodeId}/weakest?limit=${limit}`),

    getFolderCefr: (nodeId: string) =>
      apiFetch<CefrDistribution>(`/v1/folders/${nodeId}/cefr`),

    getFolderHistory: (nodeId: string, from?: string, to?: string) => {
      const params = new URLSearchParams();
      if (from) params.set("from", from);
      if (to) params.set("to", to);
      const q = params.toString();
      return apiFetch<HistoryBucketRead[]>(`/v1/folders/${nodeId}/history${q ? `?${q}` : ""}`);
    },

    // Content Acquisition & Word Generation
    searchWords: (query: string) =>
      apiFetch<WordSearchRead[]>(`/v1/words/search?q=${encodeURIComponent(query)}`),

    submitWordGeneration: (query: string) =>
      apiFetch<GenerationCreateRead>("/v1/word-generations", {
        method: "POST",
        body: JSON.stringify({ query }),
      }),

    // Study & Spaced Repetition
    startSession: (nodeId: string) =>
      apiFetch<SessionStartResponse>("/v1/sessions", {
        method: "POST",
        body: JSON.stringify({ nodeId }),
      }),

    getNextQuestion: (sessionId: string) =>
      apiFetch<NextQuestionResponse>(`/v1/sessions/${sessionId}/next`),

    submitAnswer: (sessionId: string, questionId: string, answer: string) =>
      apiFetch<GradeResponse>("/v1/answers", {
        method: "POST",
        body: JSON.stringify({ sessionId, questionId, answer }),
      }),

    getFolderStats: (nodeId: string) =>
      apiFetch<FolderStats>(`/v1/folders/${nodeId}/stats`),

    // Dashboard & Engagement
    getDashboardStats: () =>
      apiFetch<DashboardStatsRead>("/v1/learning/dashboard"),

    // Assistant & Threads
    listAssistantThreads: () =>
      apiFetch<AssistantThread[]>("/v1/assistant/threads"),

    createAssistantThread: (title?: string) =>
      apiFetch<AssistantThread>("/v1/assistant/threads", {
        method: "POST",
        body: JSON.stringify({ title }),
      }),

    getThreadMessages: (threadId: string) =>
      apiFetch<AssistantRunEvent[]>(`/v1/assistant/threads/${threadId}/messages`),

    confirmAssistantAction: (threadId: string, actionId: string, decision: "approve" | "reject") =>
      apiFetch<Record<string, unknown>>(`/v1/assistant/threads/${threadId}/actions/${actionId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      }),

    deleteAssistantThread: (threadId: string) =>
      apiFetch<void>(`/v1/assistant/threads/${threadId}`, {
        method: "DELETE",
      }),

    // Account Management & Export
    exportAccountData: () =>
      apiFetch<AccountExport>("/v1/me/export"),

    deleteAccount: (refreshToken: string) =>
      apiFetch<void>("/v1/me", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "DELETE", refresh_token: refreshToken }),
      }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
