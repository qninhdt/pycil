"use client";

import { useSystemHealth } from "@/lib/api-hooks/use-admin-system";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "ok" ? "outline" : "destructive"}>{status}</Badge>
  );
}

export default function AdminHealthPage() {
  const { data, isLoading, isError } = useSystemHealth();

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">System Health</h1>
        <p className="text-sm text-muted-foreground">
          Live status, auto-refreshing every 15s.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError || !data ? (
        <p className="text-sm text-destructive">Failed to load health.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Database
              </CardTitle>
            </CardHeader>
            <CardContent>
              <StatusBadge status={data.db} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Redis
              </CardTitle>
            </CardHeader>
            <CardContent>
              <StatusBadge status={data.redis} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Queue depth
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {data.queue_depth ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Worker heartbeat
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {data.worker_heartbeat_age_s != null
                  ? `${data.worker_heartbeat_age_s}s ago`
                  : "—"}
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
