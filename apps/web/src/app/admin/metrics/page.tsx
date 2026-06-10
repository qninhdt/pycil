"use client";

import { useAdminMetrics } from "@/lib/api-hooks/use-admin-metrics";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function Scalar({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function AdminMetricsPage() {
  const { data, isLoading, isError } = useAdminMetrics(30);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (isError || !data) {
    return <p className="text-sm text-destructive">Failed to load metrics.</p>;
  }

  const { snapshot, signup_funnel, spend_by_model, spend_by_day, top_spenders } =
    data;

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Metrics</h1>
        <p className="text-sm text-muted-foreground">
          Last {data.range_days} days. Spend figures are estimated (flat
          per-call constant).
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Scalar label="DAU" value={snapshot.dau} />
        <Scalar label="WAU" value={snapshot.wau} />
        <Scalar label="Signups today" value={snapshot.new_signups_today} />
        <Scalar label="Answers today" value={snapshot.questions_answered_today} />
        <Scalar label="Decks today" value={snapshot.decks_created_today} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Signup funnel</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">
            {signup_funnel.total_signups} signups ·{" "}
            {signup_funnel.activated} activated ·{" "}
            {(signup_funnel.activation_rate * 100).toFixed(1)}% activation
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">
            Estimated spend by model
          </h2>
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model</TableHead>
                  <TableHead className="text-right">Calls</TableHead>
                  <TableHead className="text-right">Est. $</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {spend_by_model.length ? (
                  spend_by_model.map((r) => (
                    <TableRow key={r.model}>
                      <TableCell>{r.model}</TableCell>
                      <TableCell className="text-right">{r.calls}</TableCell>
                      <TableCell className="text-right">
                        ${r.cost_usd.toFixed(4)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                      No spend yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">
            Top spenders (estimated)
          </h2>
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead className="text-right">Calls</TableHead>
                  <TableHead className="text-right">Est. $</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {top_spenders.length ? (
                  top_spenders.map((r) => (
                    <TableRow key={r.user_id}>
                      <TableCell className="font-mono text-xs">
                        {r.user_id.slice(0, 8)}
                      </TableCell>
                      <TableCell className="text-right">{r.calls}</TableCell>
                      <TableCell className="text-right">
                        ${r.cost_usd.toFixed(4)}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                      No attributed spend.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">
          Estimated spend by day
        </h2>
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Day</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Est. $</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {spend_by_day.length ? (
                spend_by_day.map((r) => (
                  <TableRow key={r.day ?? "unknown"}>
                    <TableCell>{r.day ?? "—"}</TableCell>
                    <TableCell className="text-right">{r.calls}</TableCell>
                    <TableCell className="text-right">
                      ${r.cost_usd.toFixed(4)}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground">
                    No spend in range.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  );
}
