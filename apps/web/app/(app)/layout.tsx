import React from "react";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/app-shell/app-shell";
import { getSession } from "@/lib/auth/session";
import { CentrifugoProvider } from "@/lib/realtime/provider";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session.isLoggedIn || !session.user) {
    redirect("/login");
  }

  return (
    <AppShell user={session.user}>
      <CentrifugoProvider>{children}</CentrifugoProvider>
    </AppShell>
  );
}
