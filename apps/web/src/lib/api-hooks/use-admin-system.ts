"use client";

import { useQuery } from "@tanstack/react-query";

import * as adminApi from "@/lib/api-client/admin";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.admin.health(),
    queryFn: adminApi.getHealth,
    refetchInterval: 15_000,
  });
}

export function useAuditLog(filters: {
  action?: string;
  actor?: string;
  target?: string;
}) {
  const key = JSON.stringify(filters);
  return useQuery({
    queryKey: queryKeys.admin.audit(key),
    queryFn: () => adminApi.listAudit({ ...filters, limit: 100 }),
  });
}
