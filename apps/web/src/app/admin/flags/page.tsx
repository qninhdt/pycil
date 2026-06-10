"use client";

import { useState } from "react";

import {
  useFeatureFlags,
  useCreateFlag,
  useUpdateFlag,
  useDeleteFlag,
} from "@/lib/api-hooks/use-admin-flags";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export default function AdminFlagsPage() {
  const { data, isLoading, isError } = useFeatureFlags();
  const createFlag = useCreateFlag();
  const updateFlag = useUpdateFlag();
  const deleteFlag = useDeleteFlag();

  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newRollout, setNewRollout] = useState("0");

  const [editName, setEditName] = useState<string | null>(null);
  const [editRollout, setEditRollout] = useState("0");

  const submitCreate = () => {
    const rollout = Number(newRollout);
    if (!newName.trim() || Number.isNaN(rollout)) return;
    createFlag.mutate(
      { name: newName.trim(), rollout_percentage: rollout },
      {
        onSuccess: () => {
          setCreateOpen(false);
          setNewName("");
          setNewRollout("0");
        },
      },
    );
  };

  const submitEdit = () => {
    if (editName == null) return;
    const rollout = Number(editRollout);
    if (Number.isNaN(rollout)) return;
    updateFlag.mutate(
      { name: editName, body: { rollout_percentage: rollout } },
      { onSuccess: () => setEditName(null) },
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Feature Flags</h1>
          <p className="text-sm text-muted-foreground">
            Rollout percentage gates a stable hash of the user id. Changes apply
            within ~30s across instances.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>New flag</Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Failed to load flags.</p>
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Rollout %</TableHead>
                <TableHead className="text-right">Pinned users</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.flags.length ? (
                data.flags.map((f) => (
                  <TableRow key={f.name}>
                    <TableCell className="font-medium">{f.name}</TableCell>
                    <TableCell className="text-right">
                      {f.rollout_percentage}
                    </TableCell>
                    <TableCell className="text-right">
                      {f.enabled_user_ids.length}
                    </TableCell>
                    <TableCell className="text-right space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditName(f.name);
                          setEditRollout(String(f.rollout_percentage));
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={deleteFlag.isPending}
                        onClick={() => deleteFlag.mutate(f.name)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    No flags yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New feature flag</DialogTitle>
            <DialogDescription>
              Name is immutable after creation (rename = delete + create).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="flag-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              aria-label="Flag name"
            />
            <Input
              type="number"
              min={0}
              max={100}
              placeholder="Rollout %"
              value={newRollout}
              onChange={(e) => setNewRollout(e.target.value)}
              aria-label="Rollout percentage"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={submitCreate}
              disabled={createFlag.isPending || !newName.trim()}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={editName != null} onOpenChange={(o) => !o && setEditName(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit {editName}</DialogTitle>
            <DialogDescription>Adjust the rollout percentage.</DialogDescription>
          </DialogHeader>
          <Input
            type="number"
            min={0}
            max={100}
            value={editRollout}
            onChange={(e) => setEditRollout(e.target.value)}
            aria-label="Rollout percentage"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditName(null)}>
              Cancel
            </Button>
            <Button onClick={submitEdit} disabled={updateFlag.isPending}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
