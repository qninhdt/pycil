"use client";

import { useMemo } from "react";
import { useLocalStorage } from "./use-local-storage";
import type { AppNotification, NotificationType } from "@/types/notification";

const STORAGE_KEY = "notifications";

const seedNotifications: AppNotification[] = [
  {
    id: "n1",
    type: "mention",
    title: "Alex mentioned you in a comment",
    description: '"Great set of flashcards!" on English Vocabulary',
    createdAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
    read: false,
    avatarUrl:
      "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=64&h=64&fit=crop&crop=face",
    href: "/u/alexj_study",
  },
  {
    id: "n2",
    type: "achievement",
    title: "Weekly streak reached 7 days",
    description: "Keep it up! Claim your reward",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    read: false,
    icon: "🔥",
    href: "/profile",
  },
  {
    id: "n3",
    type: "reminder",
    title: "Spaced repetition due",
    description: "15 cards are ready to review in AP Chemistry Notes",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    read: true,
    icon: "⏰",
    href: "/decks/5",
  },
  {
    id: "n4",
    type: "system",
    title: "New feature: Create shortcuts",
    description: "Quickly access decks and folders from anywhere",
    createdAt: new Date(Date.now() - 1000 * 60 * 60 * 30).toISOString(),
    read: true,
    icon: "✨",
  },
];

export function useNotifications() {
  const [items, setItems, loaded] = useLocalStorage<AppNotification[]>(
    STORAGE_KEY,
    seedNotifications
  );

  const unreadCount = useMemo(
    () => items.filter((n) => !n.read).length,
    [items]
  );

  const markAllRead = () =>
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));

  const markRead = (id: string, read = true) =>
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read } : n)));

  const clearAll = () => setItems([]);

  const addNotification = (
    n: Omit<AppNotification, "id" | "createdAt"> & {
      id?: string;
      createdAt?: string;
    }
  ) => {
    const withDefaults: AppNotification = {
      id: n.id ?? crypto.randomUUID(),
      createdAt: n.createdAt ?? new Date().toISOString(),
      ...n,
      read: (n as Partial<AppNotification>).read ?? false,
    } as AppNotification;
    setItems((prev) => [withDefaults, ...prev]);
    return withDefaults;
  };

  const byType = (type: NotificationType) =>
    items.filter((n) => n.type === type);

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
