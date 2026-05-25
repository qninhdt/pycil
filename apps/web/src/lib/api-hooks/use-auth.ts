"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as authApi from "@/lib/api-client/auth";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: authApi.getMe,
    staleTime: 5 * 60_000,
  });
}

export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) => authApi.updateMe(body),
    onSuccess: (user) => {
      qc.setQueryData(queryKeys.me(), user);
    },
  });
}
