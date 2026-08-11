"use client"

import { createContext, useContext, useEffect, useState } from "react"
import { Centrifuge, UnauthorizedError } from "centrifuge"

import { getRealtimeToken } from "@/lib/actions/realtime"

export type RealtimeConnectionState = "connecting" | "connected" | "disconnected"

interface CentrifugoContextValue {
  client: Centrifuge | null
  connectionState: RealtimeConnectionState
}

const CentrifugoContext = createContext<CentrifugoContextValue>({
  client: null,
  connectionState: "connecting",
})

/**
 * Mounted once, in the root layout. Subscriptions are opened by the components
 * that need them; this provider only owns the connection and its credentials.
 */
export function CentrifugoProvider({ children }: { children: React.ReactNode }) {
  const [client, setClient] = useState<Centrifuge | null>(null)
  const [connectionState, setConnectionState] =
    useState<RealtimeConnectionState>("connecting")

  useEffect(() => {
    let mounted = true
    let centrifuge: Centrifuge | null = null

    async function connect() {
      let initial: Awaited<ReturnType<typeof getRealtimeToken>>
      try {
        initial = await getRealtimeToken()
      } catch (error) {
        if (!mounted) return
        setConnectionState("disconnected")
        if (process.env.NODE_ENV === "development") {
          console.warn("realtime token unavailable", error)
        }
        return
      }
      if (!mounted) return
      if (!initial) {
        setConnectionState("disconnected")
        return
      }

      centrifuge = new Centrifuge(
        [{ transport: "sse", endpoint: initial.sseUrl }],
        {
          token: initial.token,
          // Realtime tokens are short-lived, so a connection that only ever
          // holds its first token dies mid-task: a grade issued fifteen
          // minutes into a session could never settle in this client. The
          // callback re-mints from the session cookie instead.
          getToken: async () => {
            const refreshed = await getRealtimeToken()
            // A missing token means the session is gone, not that the network
            // blipped. Rejecting with anything else makes Centrifugo retry
            // forever against a signed-out viewer.
            if (!refreshed) throw new UnauthorizedError("realtime token denied")
            return refreshed.token
          },
        },
      )

      centrifuge.on("connected", () => {
        if (mounted) setConnectionState("connected")
      })

      centrifuge.on("connecting", () => {
        if (mounted) setConnectionState("connecting")
      })

      centrifuge.on("disconnected", () => {
        if (mounted) setConnectionState("disconnected")
      })

      centrifuge.on("error", (context) => {
        // Recovery is enabled server-side and the subscribe proxy replays the
        // latest snapshot, so a transport error is not a lost update.
        if (process.env.NODE_ENV === "development") {
          console.warn("realtime error", context)
        }
      })

      centrifuge.connect()
      setClient(centrifuge)
    }

    void connect()

    return () => {
      mounted = false
      centrifuge?.disconnect()
      setClient(null)
    }
  }, [])

  return (
    <CentrifugoContext.Provider value={{ client, connectionState }}>
      {children}
    </CentrifugoContext.Provider>
  )
}

export function useCentrifuge() {
  return useContext(CentrifugoContext).client
}

export function useRealtimeConnectionState() {
  return useContext(CentrifugoContext).connectionState
}
