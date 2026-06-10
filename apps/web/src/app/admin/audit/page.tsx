"use client";

import { useState } from "react";

import { useAuditLog } from "@/lib/api-hooks/use-admin-system";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AdminAuditPage() {
  const [action, setAction] = useState("");
  const { data, isLoading, isError } = useAuditLog({
    action: action.trim() || undefined,
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
        <p className="text-sm text-muted-foreground">
          Append-only record of every privileged admin action.
        </p>
      </div>

      <Input
        placeholder="Filter by action (e.g. ban_user)"
        value={action}
        onChange={(e) => setAction(e.target.value)}
        className="max-w-sm"
        aria-label="Filter by action"
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Failed to load audit log.</p>
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.actions.length ? (
                data.actions.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="text-muted-foreground whitespace-nowrap">
                      {a.created_at?.replace("T", " ").slice(0, 19) ?? "—"}
                    </TableCell>
                    <TableCell className="font-medium">{a.action}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {a.actor_user_id.slice(0, 8)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {a.target_user_id ? a.target_user_id.slice(0, 8) : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {a.ip_address ?? "—"}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No audit entries.
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
