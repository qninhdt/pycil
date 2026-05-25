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
  const [uploading, setUploading] = useState(false);
  const update = useUpdateMe();

  useEffect(() => {
    if (open) setName(initialName);
  }, [open, initialName]);

  const handleImageChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error("Image must be ≤2MB.");
      return;
    }
    setUploading(true);
    try {
      const signRes = await fetch("/api/core/me/image-upload-url", {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content_type: file.type }),
      });
      if (!signRes.ok) throw new Error("sign_failed");
      const { put_url, public_url } = (await signRes.json()) as {
        put_url: string;
        public_url: string | null;
      };
      const putRes = await fetch(put_url, {
        method: "PUT",
        headers: { "content-type": file.type },
        body: file,
      });
      if (!putRes.ok) throw new Error("upload_failed");
      if (public_url) {
        await update.mutateAsync({ image_url: public_url } as any);
        toast.success("Profile image updated.");
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not upload image"));
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

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
          <div className="space-y-1.5">
            <Label htmlFor="profile-image">Profile image (≤2MB, JPEG/PNG/WebP)</Label>
            <Input
              id="profile-image"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handleImageChange}
              disabled={uploading || update.isPending}
            />
            {uploading && (
              <p className="text-xs text-muted-foreground">Uploading…</p>
            )}
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
