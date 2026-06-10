"use client";

import { useState } from "react";
import Link from "next/link";

import { useAdminUsers } from "@/lib/api-hooks/use-admin-users";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AdminUsersPage() {
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useAdminUsers(q || undefined);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
        <p className="text-sm text-muted-foreground">
          Search by email, name, or username. All access is audit-logged.
        </p>
      </div>

      <Input
        placeholder="Search users…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="max-w-sm"
        aria-label="Search users"
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Failed to load users.</p>
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.users.length ? (
                data.users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <Link
                        href={`/admin/users/${u.id}`}
                        className="font-medium hover:underline"
                      >
                        {u.email}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {u.name ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                        {u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {u.banned ? (
                        <Badge variant="destructive">banned</Badge>
                      ) : (
                        <Badge variant="outline">active</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    No users found.
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
