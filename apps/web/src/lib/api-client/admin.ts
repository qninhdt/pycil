import { fetchJson } from "./base";

export interface AdminUserListItem {
  id: string;
  email: string;
  name: string | null;
  username: string | null;
  role: string;
  banned: boolean;
  created_at: string | null;
}

export interface AdminUserSummary extends AdminUserListItem {
  banned_at: string | null;
  ban_reason: string | null;
  token_version: number;
}

export interface AdminUserJob {
  id: string;
  type: string;
  status: string;
  created_at: string | null;
}

export interface AdminUserDetail {
  user: AdminUserSummary;
  spend_today_usd: number;
  recent_jobs: AdminUserJob[];
  mastery_distribution: Record<string, number>;
}

export function listUsers(params: { q?: string; limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return fetchJson<{ users: AdminUserListItem[] }>(
    `/admin-api/users${qs ? `?${qs}` : ""}`,
  );
}

export function getUserDetail(id: string) {
  return fetchJson<AdminUserDetail>(`/admin-api/users/${id}`);
}

export function banUser(id: string, reason: string) {
  return fetchJson<{ banned: boolean; user_id: string }>(
    `/admin-api/users/${id}/ban`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
}

export function unbanUser(id: string) {
  return fetchJson<{ banned: boolean; user_id: string }>(
    `/admin-api/users/${id}/unban`,
    { method: "POST" },
  );
}

export function revokeTokens(id: string) {
  return fetchJson<{ user_id: string; token_version: number }>(
    `/admin-api/users/${id}/revoke-tokens`,
    { method: "POST" },
  );
}

export interface MetricsSnapshot {
  dau: number;
  wau: number;
  new_signups_today: number;
  questions_answered_today: number;
  decks_created_today: number;
}

export interface SignupFunnel {
  total_signups: number;
  activated: number;
  activation_rate: number;
}

export interface SpendByDay {
  day: string | null;
  cost_usd: number;
  calls: number;
}

export interface SpendByModel {
  model: string;
  cost_usd: number;
  calls: number;
}

export interface TopSpender {
  user_id: string;
  cost_usd: number;
  calls: number;
}

export interface AdminMetrics {
  range_days: number;
  snapshot: MetricsSnapshot;
  signup_funnel: SignupFunnel;
  spend_by_day: SpendByDay[];
  spend_by_model: SpendByModel[];
  top_spenders: TopSpender[];
  spend_estimated: boolean;
}

export function getMetrics(days = 30) {
  return fetchJson<AdminMetrics>(`/admin-api/metrics?days=${days}`);
}

export type ReportContentType = "deck" | "comment";

export interface CreateReportBody {
  content_type: ReportContentType;
  content_id: string;
  reason: string;
  details?: string;
}

export interface AdminReport {
  id: number;
  reporter_user_id: string;
  content_type: string;
  node_id: string | null;
  comment_id: number | null;
  reason: string;
  details: string | null;
  status: string;
  target_owner_id: string | null;
  target_snapshot: Record<string, unknown> | null;
  created_at: string | null;
}

export function createReport(body: CreateReportBody) {
  return fetchJson<{ report_id: number; status: string }>("/reports", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listReports(status = "pending") {
  return fetchJson<{ reports: AdminReport[] }>(
    `/admin-api/reports?status=${status}`,
  );
}

export function resolveReport(
  reportId: number,
  action: "dismiss" | "delete_content",
  note?: string,
) {
  return fetchJson<{ report_id: number; status: string }>(
    `/admin-api/reports/${reportId}/resolve`,
    { method: "POST", body: JSON.stringify({ action, note }) },
  );
}

export interface FeatureFlag {
  name: string;
  rollout_percentage: number;
  enabled_user_ids: string[];
  payload: Record<string, unknown>;
  updated_at: string | null;
}

export interface CreateFlagBody {
  name: string;
  rollout_percentage?: number;
  enabled_user_ids?: string[];
  payload?: Record<string, unknown>;
}

export interface UpdateFlagBody {
  rollout_percentage?: number;
  enabled_user_ids?: string[];
  payload?: Record<string, unknown>;
}

export function listFlags() {
  return fetchJson<{ flags: FeatureFlag[] }>("/admin-api/flags");
}

export function createFlag(body: CreateFlagBody) {
  return fetchJson<{ name: string; created: boolean }>("/admin-api/flags", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateFlag(name: string, body: UpdateFlagBody) {
  return fetchJson<{ name: string; updated: boolean }>(
    `/admin-api/flags/${encodeURIComponent(name)}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function deleteFlag(name: string) {
  return fetchJson<{ name: string; deleted: boolean }>(
    `/admin-api/flags/${encodeURIComponent(name)}`,
    { method: "DELETE" },
  );
}

export interface SystemHealth {
  db: string;
  redis: string;
  queue_depth: number | null;
  worker_heartbeat_age_s: number | null;
}

export function getHealth() {
  return fetchJson<SystemHealth>("/admin-api/health");
}

export interface AuditAction {
  id: number;
  actor_user_id: string;
  target_user_id: string | null;
  action: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
  ip_address: string | null;
}

export function listAudit(params: {
  limit?: number;
  cursor?: number;
  action?: string;
  actor?: string;
  target?: string;
} = {}) {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.cursor != null) search.set("cursor", String(params.cursor));
  if (params.action) search.set("action", params.action);
  if (params.actor) search.set("actor", params.actor);
  if (params.target) search.set("target", params.target);
  const qs = search.toString();
  return fetchJson<{ actions: AuditAction[]; next_cursor: number | null }>(
    `/admin-api/audit${qs ? `?${qs}` : ""}`,
  );
}
