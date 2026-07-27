"use client";

import React from "react";
import { QueryProvider } from "@/lib/query/provider";
import { UIStoreProvider } from "@/lib/stores/ui-store-provider";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryProvider>
      <UIStoreProvider>{children}</UIStoreProvider>
    </QueryProvider>
  );
}
