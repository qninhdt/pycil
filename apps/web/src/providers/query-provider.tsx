"use client";

import { useEffect, useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { setUnauthorizedHandler } from "@/lib/api-client/base";

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: 0 },
    },
  });
}

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(makeClient);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      client.clear();
      if (typeof window !== "undefined") {
        const next = encodeURIComponent(window.location.pathname);
        window.location.href = `/sign-in?reason=expired&callbackUrl=${next}`;
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [client]);

  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}
