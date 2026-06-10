"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import * as adminApi from "@/lib/api-client/admin";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useAdminUsers(q?: string) {
  return useQuery({
    queryKey: queryKeys.admin.users(q),
    queryFn: () => adminApi.listUsers({ q }),
  });
}

export function useAdminUserDetail(id: string | undefined) {
  return useQuery({
    queryKey: id ? queryKeys.admin.userDetail(id) : queryKeys.admin.userDetail("__none"),
    queryFn: () => adminApi.getUserDetail(id as string),
    enabled: !!id,
  });
}

export function useBanUser(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => adminApi.banUser(id, reason),
    onSuccess: () => {
      toast.success("User banned");
      qc.invalidateQueries({ queryKey: queryKeys.admin.userDetail(id) });
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Ban failed"),
  });
}

export function useUnbanUser(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => adminApi.unbanUser(id),
    onSuccess: () => {
      toast.success("User unbanned");
      qc.invalidateQueries({ queryKey: queryKeys.admin.userDetail(id) });
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (err) => toast.error(err instanceof Error ? err.message : "Unban failed"),
  });
}

export function useRevokeTokens(id: string) {
  return useMutation({
    mutationFn: () => adminApi.revokeTokens(id),
    onSuccess: () => toast.success("Sessions revoked"),
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Revoke failed"),
  });
}
