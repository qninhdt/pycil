import { fetchJson } from "./base";
import type { CurrentUser } from "@/types/domain";

export interface UpdateMeBody {
  name?: string;
  image_url?: string;
  bio?: string;
  study_settings?: Record<string, unknown>;
  bump_tv?: boolean;
}

export function getMe() {
  return fetchJson<CurrentUser>("/me");
}

export function updateMe(body: UpdateMeBody) {
  return fetchJson<CurrentUser>("/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
