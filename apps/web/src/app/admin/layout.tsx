import type { Metadata } from "next";
import { redirect } from "next/navigation";
import Link from "next/link";

import { auth } from "@/../auth";

export const metadata: Metadata = {
  title: "Pycil Admin",
  robots: { index: false, follow: false },
};

const NAV = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/reports", label: "Reports" },
  { href: "/admin/metrics", label: "Metrics" },
  { href: "/admin/flags", label: "Flags" },
  { href: "/admin/health", label: "Health" },
  { href: "/admin/audit", label: "Audit" },
] as const;

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Authoritative gate is the backend DB role read; this is a server-side
  // re-check so a non-admin can never render the shell even if the edge claim
  // were stale.
  const session = await auth();
  const role = (session?.user as { role?: string } | undefined)?.role;
  if (role !== "admin") {
    redirect("/");
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="flex">
        <aside className="hidden lg:flex w-56 flex-col border-r border-border bg-card px-3 py-6 min-h-screen">
          <Link
            href="/admin"
            className="px-3 pb-4 text-lg font-semibold tracking-tight"
          >
            Pycil Admin
          </Link>
          <nav className="flex flex-col gap-1">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <Link
            href="/"
            className="mt-auto px-3 pt-4 text-xs text-muted-foreground hover:text-foreground"
          >
            ← Back to app
          </Link>
        </aside>
        <main className="flex-1 p-4 lg:p-8">
          <div className="max-w-5xl mx-auto">{children}</div>
        </main>
      </div>
    </div>
  );
}
