"use client"

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react"
import { HttpAgent } from "@ag-ui/client"
import { AssistantRuntimeProvider } from "@assistant-ui/react"
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui"
import { useStore } from "zustand"

import { getThreadState } from "@/lib/actions/assistant"
import { fetchStream } from "@/lib/api/request"
import { threadMessages } from "@/lib/assistant/thread-messages"
import type { AssistantStore } from "@/lib/stores/assistant-store"

import { imageAttachmentAdapter } from "./image-attachment-adapter"

const AssistantProblemContext = createContext<string | null>(null)

export function useAssistantRuntimeProblem(): string | null {
  return useContext(AssistantProblemContext)
}

async function sendLatestTurn(
  init: RequestInit,
  selection: { model: string | null; effort: string | null },
): Promise<Response> {
  const body = JSON.parse(String(init.body)) as {
    messages: Array<{ role: string }>
    resume?: unknown[]
    forwardedProps?: Record<string, unknown>
  }
  const latest = [...body.messages].reverse().find((message) => message.role === "user")
  body.messages = body.resume?.length ? [] : latest ? [latest] : []
  // The model and effort a turn runs with ride on forwardedProps, which is the
  // AG-UI field for per-run options. They are a request, not a price: the server
  // revalidates both against its own catalog and bills from its own copy.
  body.forwardedProps = {
    ...body.forwardedProps,
    ...(selection.model ? { model: selection.model } : {}),
    ...(selection.effort ? { reasoningEffort: selection.effort } : {}),
  }
  return fetchStream("/v1/assistant/ag-ui", { ...init, body: JSON.stringify(body) })
}

export function AssistantRuntimeBridge({ children, store }: { children: React.ReactNode; store: AssistantStore }) {
  const threadId = useStore(store, (state) => state.openThreadId)
  const switchedThread = useRef<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const attachments = useMemo(() => imageAttachmentAdapter(setProblem), [])
  const agent = useMemo(() => new HttpAgent({
    url: "/v1/assistant/ag-ui",
    threadId: threadId ?? undefined,
    fetch: (_url, init) => {
      setProblem(null)
      // The selection is read from the store at request time rather than captured
      // here: a captured value would either freeze the choice or force the agent
      // to be rebuilt on every change, dropping the thread's in-flight run.
      const { selectedModel, selectedEffort } = store.getState()
      return sendLatestTurn(init, { model: selectedModel, effort: selectedEffort })
    },
  }), [store, threadId])
  const threadList = useMemo(() => ({
    threadId: threadId ?? "main",
    onSwitchToThread: async (id: string) => {
      const result = await getThreadState(id)
      if (!result.success) {
        setProblem(result.code)
        throw new Error(result.code)
      }
      setProblem(null)
      return { messages: threadMessages(result.data) }
    },
  }), [threadId])
  const runtime = useAgUiRuntime({
    agent,
    adapters: { threadList, attachments },
    onError: (error) => setProblem(error.message),
  })

  useEffect(() => {
    if (threadId && switchedThread.current !== threadId) {
      switchedThread.current = threadId
      void runtime.threads.switchToThread(threadId).catch(() => {
        switchedThread.current = null
      })
    }
  }, [runtime, threadId])

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <AssistantProblemContext.Provider value={problem}>{children}</AssistantProblemContext.Provider>
    </AssistantRuntimeProvider>
  )
}
