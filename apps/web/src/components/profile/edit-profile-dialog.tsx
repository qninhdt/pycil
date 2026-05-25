"use client";

import { useEffect, useState } from "react";
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
import { Loader2 } from "lucide-react";
import { useUpdateMe } from "@/lib/api-hooks/use-auth";
import { apiErrorMessage } from "@/lib/api-error-copy";

interface EditProfileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialName: string;
}

export function EditProfileDialog({
  open,
  onOpenChange,
  initialName,
}: EditProfileDialogProps) {
  const [name, setName] = useState(initialName);
  const update = useUpdateMe();

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  const handleSubmit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      await update.mutateAsync({ name: trimmed });
      toast.success("Profile updated. Please sign in again to refresh.");
      onOpenChange(false);
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not update profile"));
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !update.isPending && onOpenChange(o)}
    >
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Edit profile</DialogTitle>
            <DialogDescription>
              Updating your name signs you out of other devices.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="profile-name">Display name</Label>
            <Input
              id="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={1}
              maxLength={120}
              autoFocus
              disabled={update.isPending}
            />
          </div>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={update.isPending || !name.trim()}
            >
              {update.isPending && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
