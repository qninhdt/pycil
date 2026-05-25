import { fetchJson } from "./base";

export function seed() {
  return fetchJson<{ seeded: boolean }>("/onboarding/seed", { method: "POST" });
}
