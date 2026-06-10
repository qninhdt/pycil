"use client";

import { use, useState } from "react";
import Link from "next/link";

import {
  useAdminUserDetail,
  useBanUser,
  useUnbanUser,
  useRevokeTokens,
} from "@/lib/api-hooks/use-admin-users";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function AdminUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, isLoading, isError } = useAdminUserDetail(id);
  const ban = useBanUser(id);
  const unban = useUnbanUser(id);
  const revoke = useRevokeTokens(id);
  const [reason, setReason] = useState("");

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (isError || !data) {
    return <p className="text-sm text-destructive">User not found.</p>;
  }

  const { user, spend_today_usd, recent_jobs, mastery_distribution } = data;
  const isAdmin = user.role === "admin";

  return (
    <div className="space-y-6">
      <Link
        href="/admin/users"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back to users
      </Link>

      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{user.email}</h1>
          <p className="text-sm text-muted-foreground">
            {user.name ?? "—"}
            {user.username ? ` · @${user.username}` : ""}
          </p>
          <div className="flex gap-2 pt-1">
            <Badge variant={isAdmin ? "default" : "secondary"}>{user.role}</Badge>
            {user.banned ? (
              <Badge variant="destructive">banned</Badge>
            ) : (
              <Badge variant="outline">active</Badge>
            )}
          </div>
        </div>
      </div>

      {user.banned && user.ban_reason ? (
        <p className="text-sm text-muted-foreground">
          Ban reason: <span className="text-foreground">{user.ban_reason}</span>
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Spend today (estimated)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              ${spend_today_usd.toFixed(4)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mastery levels
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              {Object.keys(mastery_distribution).length
                ? Object.entries(mastery_distribution)
                    .map(([lvl, n]) => `L${lvl}: ${n}`)
                    .join(" · ")
                : "No data"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Token version
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{user.token_version}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent jobs</CardTitle>
        </CardHeader>
        <CardContent>
          {recent_jobs.length ? (
            <ul className="space-y-1 text-sm">
              {recent_jobs.map((j) => (
                <li key={j.id} className="flex justify-between gap-4">
                  <span>{j.type}</span>
                  <span className="text-muted-foreground">{j.status}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No recent jobs.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Moderation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isAdmin ? (
            <p className="text-sm text-muted-foreground">
              This account is an admin. Demote it before banning or revoking.
            </p>
          ) : user.banned ? (
            <Button
              variant="outline"
              onClick={() => unban.mutate()}
              disabled={unban.isPending}
            >
              Unban user
            </Button>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                placeholder="Ban reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="max-w-xs"
                aria-label="Ban reason"
              />
              <Button
                variant="destructive"
                onClick={() => ban.mutate(reason)}
                disabled={ban.isPending || reason.trim().length === 0}
              >
                Ban user
              </Button>
            </div>
          )}

          {!isAdmin ? (
            <Button
              variant="outline"
              onClick={() => revoke.mutate()}
              disabled={revoke.isPending}
            >
              Revoke all sessions
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
