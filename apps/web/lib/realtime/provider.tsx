"use client";

import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Centrifuge } from "centrifuge";
import { getRealtimeToken } from "@/lib/actions/realtime";
import type { RealtimeToken } from "@/lib/api/types";

export type RealtimeConnectionState = "connecting" | "connected" | "disconnected";

interface CentrifugoContextValue {
  client: Centrifuge | null;
  connectionState: RealtimeConnectionState;
}

const CentrifugoContext = createContext<CentrifugoContextValue>({
  client: null,
  connectionState: "connecting",
});

export function CentrifugoProvider({ children }: { children: React.ReactNode }) {
  const centrifugeRef = useRef<Centrifuge | null>(null);
  const [client, setClient] = useState<Centrifuge | null>(null);
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>("connecting");

  useEffect(() => {
    let mounted = true;

    async function initRealtime() {
      const tokenData: RealtimeToken | null = await getRealtimeToken();
      if (!tokenData || !mounted) {
        if (mounted) setConnectionState("disconnected");
        return;
      }

      try {
        const centrifuge = new Centrifuge([{ transport: "sse", endpoint: tokenData.sseUrl }], {
          token: tokenData.token,
        });

        centrifuge.on("connected", (ctx) => {
          if (mounted) setConnectionState("connected");
          if (process.env.NODE_ENV === "development") {
            console.log("Connected to Centrifugo:", ctx);
          }
        });

        centrifuge.on("disconnected", (ctx) => {
          if (mounted) setConnectionState("disconnected");
          if (process.env.NODE_ENV === "development") {
            console.warn("Disconnected from Centrifugo:", ctx);
          }
        });

        centrifuge.on("error", (err) => {
          console.warn("Centrifugo connection error:", err);
        });

        centrifuge.connect();
        centrifugeRef.current = centrifuge;
        setClient(centrifuge);
      } catch (err) {
        if (mounted) setConnectionState("disconnected");
        console.warn("Failed to initialize Centrifugo client:", err);
      }
    }

    initRealtime();

    return () => {
      mounted = false;
      if (centrifugeRef.current) {
        centrifugeRef.current.disconnect();
        centrifugeRef.current = null;
      }
    };
  }, []);

  return (
    <CentrifugoContext.Provider value={{ client, connectionState }}>
      {children}
    </CentrifugoContext.Provider>
  );
}

export function useCentrifuge() {
  return useContext(CentrifugoContext).client;
}

export function useRealtimeConnectionState() {
  return useContext(CentrifugoContext).connectionState;
}
