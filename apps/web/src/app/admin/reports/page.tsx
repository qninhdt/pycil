"use client";

import { useState } from "react";

import {
  useAdminReports,
  useResolveReport,
} from "@/lib/api-hooks/use-admin-reports";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const STATUSES = ["pending", "actioned", "dismissed"] as const;

export default function AdminReportsPage() {
  const [status, setStatus] = useState<string>("pending");
  const { data, isLoading, isError } = useAdminReports(status);
  const resolve = useResolveReport(status);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          Triage user-submitted content reports. Deletes are reversible
          soft-deletes.
        </p>
      </div>

      <div className="flex gap-2">
        {STATUSES.map((s) => (
          <Button
            key={s}
            variant={status === s ? "default" : "outline"}
            size="sm"
            onClick={() => setStatus(s)}
          >
            {s}
          </Button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Failed to load reports.</p>
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Reported</TableHead>
                {status === "pending" ? (
                  <TableHead className="text-right">Actions</TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.reports.length ? (
                data.reports.map((r) => {
                  const targetLabel =
                    (r.target_snapshot?.name as string | undefined) ??
                    (r.target_snapshot?.excerpt as string | undefined) ??
                    r.node_id ??
                    (r.comment_id != null ? `comment #${r.comment_id}` : "—");
                  return (
                    <TableRow key={r.id}>
                      <TableCell>
                        <Badge variant="secondary">{r.content_type}</Badge>
                      </TableCell>
                      <TableCell className="max-w-[16rem] truncate">
                        {targetLabel}
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{r.reason}</span>
                        {r.details ? (
                          <span className="block text-xs text-muted-foreground">
                            {r.details}
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {r.created_at?.slice(0, 10) ?? "—"}
                      </TableCell>
                      {status === "pending" ? (
                        <TableCell className="text-right space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={resolve.isPending}
                            onClick={() =>
                              resolve.mutate({
                                reportId: r.id,
                                action: "dismiss",
                              })
                            }
                          >
                            Dismiss
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={resolve.isPending}
                            onClick={() =>
                              resolve.mutate({
                                reportId: r.id,
                                action: "delete_content",
                              })
                            }
                          >
                            Delete content
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell
                    colSpan={status === "pending" ? 5 : 4}
                    className="text-center text-muted-foreground"
                  >
                    No {status} reports.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
