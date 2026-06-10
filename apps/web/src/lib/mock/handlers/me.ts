// Mock handlers for /me + /onboarding/seed — mirrors routes/auth.py + onboarding.

import { getState, commit } from "../store";
import type { CurrentUser } from "@/types/domain";

interface UpdateMeBody {
  name?: string;
  image_url?: string;
  bio?: string;
  study_settings?: Record<string, unknown>;
  bump_tv?: boolean;
}

function toCurrentUser(): CurrentUser {
  const { user } = getState();
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    image: user.image,
    image_url: user.image_url,
  };
}

export function getMe(): CurrentUser {
  return toCurrentUser();
}

export function updateMe(body: UpdateMeBody): CurrentUser {
  const state = getState();
  if (body.name !== undefined) state.user.name = body.name;
  if (body.image_url !== undefined) {
    state.user.image_url = body.image_url;
    state.user.image = body.image_url;
  }
  if (body.bio !== undefined) state.user.bio = body.bio;
  if (body.study_settings !== undefined) {
    state.user.study_settings = body.study_settings;
  }
  commit();
  return toCurrentUser();
}

export function seedOnboarding(): { seeded: boolean } {
  // Seed already ran on store init; nothing to do.
  return { seeded: true };
}
