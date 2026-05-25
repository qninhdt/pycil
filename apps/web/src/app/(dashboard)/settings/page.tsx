"use client";

import { ThemeSection } from "@/components/settings/theme-section";
import { AccountSection } from "@/components/settings/account-section";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <ThemeSection />
      <AccountSection />
    </div>
  );
}
