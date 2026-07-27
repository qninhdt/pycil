"use client";

import React from "react";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import type { SessionUser } from "@/lib/auth/types";
import { AppSidebar } from "./app-sidebar";
import { TopBar } from "./top-bar";

export function AppShell({
  user,
  children,
}: {
  user?: SessionUser;
  children: React.ReactNode;
}) {
  return (
    <SidebarProvider defaultOpen>
      <AppSidebar user={user} />
      <SidebarInset>
        <TopBar user={user} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
