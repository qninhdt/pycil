import { getSession } from "@/lib/auth/session";
import { DataExportCard } from "@/components/settings/data-export-card";
import { DeleteAccountModal } from "@/components/settings/delete-account-modal";
import { ProfileCard } from "@/components/settings/profile-card";

export const metadata = {
  title: "Account Settings - Pycil",
  description: "Manage your profile, account preferences, data export, and deletion.",
};

export default async function SettingsPage() {
  const session = await getSession();

  const user = session.user
    ? {
        id: session.user.id,
        email: session.user.email,
        name: session.user.name ?? null,
        image: session.user.image ?? null,
        tokenVersion: session.user.tokenVersion ?? 1,
      }
    : null;

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100">
          Account Settings
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Manage your account details, privacy options, data export, and security.
        </p>
      </div>

      {/* User Profile Overview */}
      <ProfileCard user={user} />

      {/* Data Export Card */}
      <DataExportCard />

      {/* Danger Zone: Account Deletion */}
      <DeleteAccountModal />
    </div>
  );
}
