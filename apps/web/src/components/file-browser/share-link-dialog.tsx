"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Copy, Trash2 } from "lucide-react";
import { toast } from "sonner";

type Link = {
  id: string;
  token: string;
  created_at: string;
  revoked_at: string | null;
};

interface ShareLinkDialogProps {
  nodeId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ShareLinkDialog({ nodeId, open, onOpenChange }: ShareLinkDialogProps) {
  const [links, setLinks] = useState<Link[]>([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const res = await fetch(`/api/core/nodes/${nodeId}/share-links`, {
      credentials: "include",
    });
    if (res.ok) setLinks(await res.json());
  };

  useEffect(() => {
    if (open) void load();
  }, [open, nodeId]);

  const create = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/api/core/nodes/${nodeId}/share-links`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) {
        await load();
        toast.success("Share link created");
      }
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string) => {
    setBusy(true);
    try {
      const res = await fetch(`/api/core/nodes/share-links/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok) {
        await load();
        toast.success("Link revoked");
      }
    } finally {
      setBusy(false);
    }
  };

  const copy = async (token: string) => {
    const url = `${window.location.origin}/share/${token}`;
    await navigator.clipboard.writeText(url);
    toast.success("Copied to clipboard");
  };

  const active = links.filter((l) => !l.revoked_at);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Share this</DialogTitle>
          <DialogDescription>
            Anyone with the link can view a read-only snapshot.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {active.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active links.</p>
          ) : (
            active.map((l) => {
              const url = `${typeof window !== "undefined" ? window.location.origin : ""}/share/${l.token}`;
              return (
                <div key={l.id} className="flex gap-2">
                  <Input value={url} readOnly />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => copy(l.token)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => revoke(l.id)}
                    disabled={busy}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              );
            })
          )}

          <Button onClick={create} disabled={busy} className="w-full">
            Create new link
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
