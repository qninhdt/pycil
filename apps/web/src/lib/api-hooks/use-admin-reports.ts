"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import * as adminApi from "@/lib/api-client/admin";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useCreateReport() {
  return useMutation({
    mutationFn: (body: adminApi.CreateReportBody) => adminApi.createReport(body),
    onSuccess: () => toast.success("Report submitted. Thanks for flagging this."),
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Report failed"),
  });
}

export function useAdminReports(status = "pending") {
  return useQuery({
    queryKey: queryKeys.admin.reports(status),
    queryFn: () => adminApi.listReports(status),
  });
}

export function useResolveReport(status = "pending") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      reportId,
      action,
      note,
    }: {
      reportId: number;
      action: "dismiss" | "delete_content";
      note?: string;
    }) => adminApi.resolveReport(reportId, action, note),
    onSuccess: (res) => {
      toast.success(`Report ${res.status}`);
      qc.invalidateQueries({ queryKey: queryKeys.admin.reports(status) });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Resolve failed"),
  });
}
