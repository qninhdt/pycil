"use client";

import { signOut } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LogOut, ShieldAlert, Trash2 } from "lucide-react";
import { useMe } from "@/lib/api-hooks/use-auth";

async function patchMe(body: Record<string, unknown>) {
  const res = await fetch("/api/core/me", {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`patch_me_failed_${res.status}`);
  return res.json();
}

async function deleteMe() {
  const res = await fetch("/api/core/me", {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`delete_me_failed_${res.status}`);
}

export function AccountSection() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<"signout" | "everywhere" | "delete" | null>(null);

  const handleSignOut = async () => {
    setBusy("signout");
    qc.clear();
    await signOut({ callbackUrl: "/sign-in" });
  };

  const handleSignOutEverywhere = async () => {
    setBusy("everywhere");
    try {
      await patchMe({ bump_tv: true });
      qc.clear();
      await signOut({ callbackUrl: "/sign-in?reason=token_revoked" });
    } catch {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(
      "Delete your account? This is reversible within 14 days; after that the data is permanently removed."
    )) {
      return;
    }
    setBusy("delete");
    try {
      await deleteMe();
      qc.clear();
      await signOut({ callbackUrl: "/?account_deleted=1" });
    } catch {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Email
          </p>
          <p className="text-sm">{me?.email ?? "—"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleSignOut} disabled={busy !== null}>
            <LogOut className="h-4 w-4 mr-2" />
            Sign out
          </Button>
          <Button
            variant="outline"
            onClick={handleSignOutEverywhere}
            disabled={busy !== null}
          >
            <ShieldAlert className="h-4 w-4 mr-2" />
            Sign out everywhere
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={busy !== null}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Delete account
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
