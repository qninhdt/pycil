"use client";

import { AlertTriangle } from "lucide-react";
import type { NodeItem } from "@/lib/api/types";
import { useDeleteNode } from "@/lib/query/nodes";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface DeleteNodeDialogProps {
  node: NodeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteNodeDialog({ node, open, onOpenChange }: DeleteNodeDialogProps) {
  const deleteNode = useDeleteNode();

  const handleDelete = () => {
    if (!node) return;
    deleteNode.mutate(node.id, {
      onSuccess: () => {
        onOpenChange(false);
      },
    });
  };

  if (!node) return null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Delete {node.type === "FOLDER" ? "Folder" : "Deck"}
          </AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete &ldquo;{node.name}&rdquo;?
            {node.type === "FOLDER" && " All nested contents inside this folder will be deleted."}
            {" "}This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleteNode.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleteNode.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleteNode.isPending ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
