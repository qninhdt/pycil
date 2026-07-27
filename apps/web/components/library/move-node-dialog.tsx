"use client";

import { useState } from "react";
import { Move } from "lucide-react";
import type { NodeItem } from "@/lib/api/types";
import { useMoveNode, useNodes } from "@/lib/query/nodes";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";

interface MoveNodeDialogProps {
  node: NodeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MoveNodeDialog({ node, open, onOpenChange }: MoveNodeDialogProps) {
  const [selectedParentId, setSelectedParentId] = useState<string>("root");
  const moveNode = useMoveNode();
  const { data: rootNodes } = useNodes(null);

  const availableFolders = rootNodes?.items.filter(
    (item) => item.type === "FOLDER" && item.id !== node?.id
  ) || [];

  const handleMove = () => {
    if (!node) return;
    const parentNodeId = selectedParentId === "root" ? null : selectedParentId;

    moveNode.mutate(
      {
        id: node.id,
        data: { parentNodeId },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  if (!node) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Move className="h-5 w-5 text-primary" />
            Move &ldquo;{node.name}&rdquo;
          </DialogTitle>
          <DialogDescription>
            Select a destination folder or move to root library level.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-3">
          <div className="space-y-2">
            <Label htmlFor="destination-folder">Destination</Label>
            <NativeSelect
              id="destination-folder"
              value={selectedParentId}
              onChange={(e) => setSelectedParentId(e.target.value)}
            >
              <option value="root">📁 Library Root (Top Level)</option>
              {availableFolders.map((folder) => (
                <option key={folder.id} value={folder.id}>
                  📁 {folder.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={moveNode.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleMove} disabled={moveNode.isPending}>
            {moveNode.isPending ? "Moving..." : "Move Here"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
