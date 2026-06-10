"use client";

import { ThemeSection } from "@/components/settings/theme-section";
import { AccountSection } from "@/components/settings/account-section";

export default function SettingsPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Customize your appearance and manage your account.
        </p>
      </header>
      <ThemeSection />
      <AccountSection />
    </div>
  );
}
