"use client";

import { Mail, Shield, User as UserIcon } from "lucide-react";
import type { User } from "@/lib/api/types";

interface ProfileCardProps {
  user: User | null;
}

export function ProfileCard({ user }: ProfileCardProps) {
  return (
    <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-xs space-y-4">
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold text-xl">
          {user?.name ? user.name[0].toUpperCase() : user?.email ? user.email[0].toUpperCase() : "U"}
        </div>
        <div>
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {user?.name || "Learner"}
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5 mt-0.5">
            <Mail className="w-3.5 h-3.5" />
            {user?.email || "No email available"}
          </p>
        </div>
      </div>

      <div className="pt-4 border-t border-neutral-100 dark:border-neutral-800 flex items-center justify-between text-xs text-neutral-500">
        <span className="flex items-center gap-1">
          <Shield className="w-3.5 h-3.5 text-emerald-500" />
          PKCE Bearer Verified
        </span>
        <span>Token Version: {user?.tokenVersion ?? 1}</span>
      </div>
    </div>
  );
}
