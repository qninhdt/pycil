"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import * as adminApi from "@/lib/api-client/admin";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useFeatureFlags() {
  return useQuery({
    queryKey: queryKeys.admin.flags(),
    queryFn: adminApi.listFlags,
  });
}

export function useCreateFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: adminApi.CreateFlagBody) => adminApi.createFlag(body),
    onSuccess: () => {
      toast.success("Flag created");
      qc.invalidateQueries({ queryKey: queryKeys.admin.flags() });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Create failed"),
  });
}

export function useUpdateFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, body }: { name: string; body: adminApi.UpdateFlagBody }) =>
      adminApi.updateFlag(name, body),
    onSuccess: () => {
      toast.success("Flag updated");
      qc.invalidateQueries({ queryKey: queryKeys.admin.flags() });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Update failed"),
  });
}

export function useDeleteFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => adminApi.deleteFlag(name),
    onSuccess: () => {
      toast.success("Flag deleted");
      qc.invalidateQueries({ queryKey: queryKeys.admin.flags() });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Delete failed"),
  });
}
