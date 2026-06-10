import type { UUID } from "./node";

export interface CurrentUser {
  id: UUID;
  email: string;
  name: string | null;
  image: string | null;
  image_url?: string | null;
  // Gamification fields are not yet returned by the API (deferred feature).
  // Typed optional so the profile UI can render with safe defaults without
  // `any` casts; they read as `undefined` until the backend supplies them.
  level?: number;
  xp_total?: number;
  streak_days?: number;
  league_rank?: number;
  badges?: string[];
}
