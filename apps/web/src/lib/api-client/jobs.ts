import { fetchJson, streamUrl } from "./base";
import type { JobRow } from "@/types/domain";

export function getJob(id: string) {
  return fetchJson<JobRow>(`/jobs/${id}`);
}

export function jobStreamUrl(id: string): string {
  return streamUrl(`/jobs/${id}/stream`);
}
