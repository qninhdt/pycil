"use client";

import { useQuery } from "@tanstack/react-query";

import * as adminApi from "@/lib/api-client/admin";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useAdminMetrics(days = 30) {
  return useQuery({
    queryKey: queryKeys.admin.metrics(days),
    queryFn: () => adminApi.getMetrics(days),
    staleTime: 30_000,
  });
}
