"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Edit } from "lucide-react";
import { useState } from "react";
import { useMe } from "@/lib/api-hooks/use-auth";
import { EditProfileDialog } from "@/components/profile/edit-profile-dialog";

function initialsFrom(name: string | null | undefined, email: string): string {
  const source = name?.trim() || email.split("@")[0];
  return source
    .split(/\s+/)
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

export default function ProfilePage() {
  const { data: me, isLoading } = useMe();
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading profile…</p>;
  }
  if (!me) {
    return <p className="text-sm text-destructive">Could not load profile.</p>;
  }

  const displayName = me.name?.trim() || me.email.split("@")[0];

  return (
    <div className="space-y-6">
      <Card>
        <div className="h-32 bg-gradient-to-r from-primary/20 to-primary/10 rounded-t-lg" />
        <CardContent className="relative pt-0 px-4 sm:px-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4 -mt-12">
            <Avatar className="w-24 h-24 border-4 border-background shadow-lg">
              {me.image && <AvatarImage src={me.image} alt={displayName} />}
              <AvatarFallback className="text-2xl">
                {initialsFrom(me.name, me.email)}
              </AvatarFallback>
            </Avatar>

            <div className="flex-1 min-w-0 pt-12 sm:pt-0">
              <h1 className="text-2xl font-bold">{displayName}</h1>
              <p className="text-muted-foreground">{me.email}</p>
            </div>

            <Button
              variant="outline"
              className="mt-4 sm:mt-0 shrink-0"
              onClick={() => setEditOpen(true)}
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit profile
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Stats</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Stat label="Level" value={String((me as any).level ?? 1)} />
            <Stat label="XP" value={String((me as any).xp_total ?? 0)} />
            <Stat
              label="Streak"
              value={`${(me as any).streak_days ?? 0}d`}
            />
            <Stat
              label="Rank"
              value={
                (me as any).league_rank
                  ? `#${(me as any).league_rank}`
                  : "—"
              }
            />
          </div>
          {Array.isArray((me as any).badges) && (me as any).badges.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {((me as any).badges as string[]).map((b) => (
                <Badge key={b} variant="secondary">
                  {b.replace(/_/g, " ")}
                </Badge>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <EditProfileDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initialName={me.name ?? ""}
      />
    </div>
  );
}
