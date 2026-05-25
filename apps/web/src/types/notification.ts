export type NotificationType =
  | "mention"
  | "system"
  | "achievement"
  | "reminder";

export interface AppNotification {
  id: string;
  type: NotificationType;
  title: string;
  description?: string;
  createdAt: string; // ISO string
  read: boolean;
  href?: string;
  icon?: string; // emoji fallback when no avatar
  avatarUrl?: string;
  meta?: Record<string, string | number | boolean>;
}
