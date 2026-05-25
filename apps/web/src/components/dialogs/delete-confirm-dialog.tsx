"use client";

import { useState } from "react";
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
import { useDeleteNode } from "@/lib/api-hooks/use-nodes";
import { apiErrorMessage } from "@/lib/api-error-copy";
import type { UUID } from "@/types/domain";
import { Loader2, Trash2 } from "lucide-react";

interface DeleteConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  nodeId: UUID;
  nodeName: string;
  isFolder: boolean;
  childCount?: number;
  onDeleted?: () => void;
}

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  nodeId,
  nodeName,
  isFolder,
  childCount,
  onDeleted,
}: DeleteConfirmDialogProps) {
  const [submitting, setSubmitting] = useState(false);
  const deleteNode = useDeleteNode();

  const handleDelete = async () => {
    setSubmitting(true);
    try {
      await deleteNode.mutateAsync(nodeId);
      toast.success(`Deleted "${nodeName}"`);
      onOpenChange(false);
      onDeleted?.();
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not delete"));
    } finally {
      setSubmitting(false);
    }
  };

  const description = isFolder
    ? typeof childCount === "number"
      ? `Delete "${nodeName}" and its ${childCount} ${
          childCount === 1 ? "item" : "items"
        }? This cannot be undone.`
      : `Delete "${nodeName}" and all its contents? This cannot be undone.`
    : `Delete "${nodeName}" and all its terms? This cannot be undone.`;

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            {isFolder ? "Delete folder" : "Delete deck"}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={submitting}
          >
            {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
