"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateNode, useRootNodes } from "@/lib/api-hooks/use-nodes";
import { apiErrorMessage } from "@/lib/api-error-copy";
import type { UUID } from "@/types/domain";
import { Loader2 } from "lucide-react";

interface CreateShortcutDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parentNodeId?: UUID | null;
  onCreated?: (nodeId: UUID) => void;
}

/** Create a SHORTCUT node pointing at one of the user's existing folders/decks.
 *
 * The target picker lists the user's root-level nodes (the common case). A SERIAL
 * id is server-assigned; the service validates target ownership before linking,
 * so an unowned/unknown target is rejected server-side regardless of this list. */
export function CreateShortcutDialog({
  open,
  onOpenChange,
  parentNodeId = null,
  onCreated,
}: CreateShortcutDialogProps) {
  const [name, setName] = useState("");
  const [targetId, setTargetId] = useState<UUID | "">("");
  const [submitting, setSubmitting] = useState(false);
  const createNode = useCreateNode();
  const rootNodes = useRootNodes();

  // Shortcuts can only point at folders/decks, never another shortcut.
  const targets = useMemo(
    () => (rootNodes.data ?? []).filter((n) => n.type !== "SHORTCUT"),
    [rootNodes.data],
  );

  useEffect(() => {
    if (open) {
      setName("");
      setTargetId("");
      setSubmitting(false);
    }
  }, [open]);

  const handleSubmit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || !targetId) return;
    setSubmitting(true);
    try {
      const node = await createNode.mutateAsync({
        type: "SHORTCUT",
        name: trimmed,
        parent_node_id: parentNodeId,
        target_node_id: targetId,
      });
      toast.success(`Created shortcut "${node.name}"`);
      onOpenChange(false);
      onCreated?.(node.id);
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not create shortcut"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New shortcut</DialogTitle>
            <DialogDescription>
              A shortcut points at one of your folders or decks so you can reach
              it from another location.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="shortcut-name">Name</Label>
              <Input
                id="shortcut-name"
                name="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Quick link"
                required
                minLength={1}
                maxLength={100}
                autoFocus
                disabled={submitting}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="shortcut-target">Target</Label>
              <select
                id="shortcut-target"
                value={targetId}
                onChange={(e) => setTargetId(e.target.value as UUID)}
                required
                disabled={submitting || rootNodes.isLoading}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="" disabled>
                  {rootNodes.isLoading ? "Loading…" : "Select a folder or deck"}
                </option>
                {targets.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.type === "FOLDER" ? "📁 " : "📄 "}
                    {n.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !name.trim() || !targetId}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
