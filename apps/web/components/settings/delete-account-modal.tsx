"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { deleteAccountAction } from "@/lib/actions/account";

export function DeleteAccountModal() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [confirmInput, setConfirmInput] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (confirmInput !== "DELETE") return;
    setIsDeleting(true);
    setError(null);
    const res = await deleteAccountAction();
    if (res.success) {
      router.push("/login");
    } else {
      setError(res.error || "Failed to delete account");
      setIsDeleting(false);
    }
  }

  return (
    <>
      <div className="p-6 rounded-2xl border border-red-200 bg-red-50/50 dark:bg-red-950/30 dark:border-red-900 shadow-xs space-y-4">
        <div className="flex items-start gap-3">
          <div className="p-3 rounded-xl bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400">
            <Trash2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-red-950 dark:text-red-100">
              Danger Zone: Delete Account
            </h3>
            <p className="mt-1 text-sm text-red-900/80 dark:text-red-300">
              Permanently remove your account, decks, FSRS memory statistics, and all personal data. This action cannot be undone.
            </p>
          </div>
        </div>

        <div className="pt-2">
          <button
            type="button"
            onClick={() => setIsOpen(true)}
            className="px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white font-medium text-sm transition-colors"
          >
            Delete Account
          </button>
        </div>
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
              <AlertTriangle className="w-6 h-6" />
              <h3 className="text-lg font-bold text-neutral-900 dark:text-neutral-100">
                Confirm Account Deletion
              </h3>
            </div>

            <p className="text-sm text-neutral-600 dark:text-neutral-400">
              To confirm deletion, please type <span className="font-mono font-bold text-red-600 dark:text-red-400">DELETE</span> in the field below.
            </p>

            <input
              type="text"
              value={confirmInput}
              onChange={(e) => setConfirmInput(e.target.value)}
              placeholder="Type DELETE to confirm"
              className="w-full px-4 py-2.5 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-950 font-mono text-sm focus:outline-hidden focus:ring-2 focus:ring-red-500"
            />

            {error && (
              <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => {
                  setIsOpen(false);
                  setConfirmInput("");
                  setError(null);
                }}
                className="px-4 py-2 rounded-xl border border-neutral-200 dark:border-neutral-800 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={confirmInput !== "DELETE" || isDeleting}
                onClick={handleDelete}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm font-medium transition-colors disabled:opacity-50"
              >
                {isDeleting && <Loader2 className="w-4 h-4 animate-spin" />}
                Confirm Deletion
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
