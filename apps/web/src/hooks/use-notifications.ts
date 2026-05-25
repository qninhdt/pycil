"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { AppNotification, NotificationType } from "@/types/notification";

type ServerNotification = {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

function kindToType(kind: string): NotificationType {
  if (kind.startsWith("badge")) return "achievement";
  if (kind.startsWith("mention")) return "mention";
  if (kind.startsWith("reminder") || kind === "review_due") return "reminder";
  return "system";
}

function fromServer(n: ServerNotification): AppNotification {
  const title = String(n.payload.title ?? n.kind);
  const description =
    typeof n.payload.description === "string"
      ? (n.payload.description as string)
      : undefined;
  return {
    id: n.id,
    type: kindToType(n.kind),
    title,
    description,
    createdAt: n.created_at,
    read: n.read_at !== null,
    href: typeof n.payload.href === "string" ? (n.payload.href as string) : undefined,
    icon: typeof n.payload.icon === "string" ? (n.payload.icon as string) : undefined,
  };
}

const POLL_MS = 30_000;

export function useNotifications() {
  const [items, setItems] = useState<AppNotification[]>([]);
  const [loaded, setLoaded] = useState(false);

  const fetchPage = useCallback(async () => {
    try {
      const res = await fetch("/api/core/notifications?limit=50", {
        credentials: "include",
      });
      if (!res.ok) return;
      const data = (await res.json()) as ServerNotification[];
      setItems(data.map(fromServer));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void fetchPage();
    const id = setInterval(fetchPage, POLL_MS);
    return () => clearInterval(id);
  }, [fetchPage]);

  const unreadCount = useMemo(
    () => items.filter((n) => !n.read).length,
    [items]
  );

  const markAllRead = useCallback(async () => {
    const unreadIds = items.filter((n) => !n.read).map((n) => n.id);
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    if (unreadIds.length === 0) return;
    await fetch("/api/core/notifications/mark-read", {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ids: unreadIds }),
    }).catch(() => undefined);
  }, [items]);

  const markRead = useCallback(
    async (id: string, read = true) => {
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read } : n)));
      if (!read) return;
      await fetch("/api/core/notifications/mark-read", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ ids: [id] }),
      }).catch(() => undefined);
    },
    []
  );

  const clearAll = useCallback(() => setItems([]), []);

  const addNotification = useCallback(
    (n: Omit<AppNotification, "id" | "createdAt"> & { id?: string; createdAt?: string }) => {
      const withDefaults: AppNotification = {
        id: n.id ?? crypto.randomUUID(),
        createdAt: n.createdAt ?? new Date().toISOString(),
        ...n,
        read: (n as Partial<AppNotification>).read ?? false,
      } as AppNotification;
      setItems((prev) => [withDefaults, ...prev]);
      return withDefaults;
    },
    []
  );

  const byType = useCallback(
    (type: NotificationType) => items.filter((n) => n.type === type),
    [items]
  );

  return {
    items,
    unreadCount,
    loaded,
    markAllRead,
    markRead,
    clearAll,
    addNotification,
    byType,
  } as const;
}
