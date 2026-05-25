import { fetchJson } from "./base";
import type { CurrentUser } from "@/types/domain";

export function getMe() {
  return fetchJson<CurrentUser>("/me");
}

export function updateMe(body: { name: string }) {
  return fetchJson<CurrentUser>("/me", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
