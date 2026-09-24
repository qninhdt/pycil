import type { ThreadMessage } from "@assistant-ui/react"

import type { ThreadState } from "@/lib/api/resources/assistant"

import { approvalAction, type InterruptLike } from "./approval-action"

function contentText(value: unknown): string {
  if (typeof value === "string") return value
  if (Array.isArray(value)) {
    return value.map((part) => typeof part === "string" ? part :
      part && typeof part === "object" && "text" in part ? String(part.text) : "").join("")
  }
  return value == null ? "" : JSON.stringify(value)
}

function imageAttachments(content: unknown) {
  if (!Array.isArray(content)) return []
  return content.flatMap((part, index) => {
    if (!part || typeof part !== "object") return []
    const item = part as Record<string, unknown>
    const source = item.source && typeof item.source === "object"
      ? item.source as Record<string, unknown>
      : null
    const imageUrl = item.image_url && typeof item.image_url === "object"
      ? (item.image_url as Record<string, unknown>).url
      : item.image_url
    const data = typeof imageUrl === "string" ? imageUrl
      : source?.type === "data" && typeof source.value === "string" && typeof source.mimeType === "string"
        ? `data:${source.mimeType};base64,${source.value}`
        : null
    if (!data || !/^data:image\/(jpeg|png|webp);base64,/.test(data)) return []
    return [{
      id: `image-${index}`,
      type: "image" as const,
      name: "Attached image",
      contentType: data.slice(5, data.indexOf(";")),
      status: { type: "complete" as const },
      content: [{ type: "image" as const, image: data }],
    }]
  })
}

/** Translate persisted LangChain messages to assistant-ui's message contract. */
export function threadMessages(state: ThreadState): ThreadMessage[] {
  const messages = state.messages.flatMap<ThreadMessage>((message, index) => {
    const type = message.type
    if (type === "system") return []
    const isUser = type === "human" || type === "user"
    const text = type === "tool"
      ? `${String(message.name ?? "Tool")} result: ${contentText(message.content)}`
      : contentText(message.content)
    const toolCalls = Array.isArray(message.tool_calls)
      ? message.tool_calls.map((call) => {
          if (!call || typeof call !== "object") return ""
          const item = call as Record<string, unknown>
          return `${String(item.name ?? "Tool")}: ${JSON.stringify(item.args ?? {})}`
        }).filter(Boolean).join("\n")
      : ""
    const body = [text, toolCalls].filter(Boolean).join("\n")
    const attachments = isUser ? imageAttachments(message.content) : []
    if (!body && attachments.length === 0) return []
    const common = {
      id: typeof message.id === "string" ? message.id : `thread-${index}`,
      content: [{ type: "text" as const, text: body }],
      createdAt: new Date(0),
      metadata: { custom: {} },
    }
    return isUser
      ? [{ ...common, role: "user" as const, attachments } as ThreadMessage]
      : [{
          ...common,
          role: "assistant" as const,
          status: { type: "complete" as const, reason: "stop" as const },
          metadata: {
            custom: {},
            unstable_state: null,
            unstable_annotations: [],
            unstable_data: [],
            steps: [],
            submittedFeedback: undefined,
            timing: undefined,
          },
        } as ThreadMessage]
  })
  if (state.status !== "interrupted" || !state.interrupts.length) {
    return messages
  }

  const interrupt = state.interrupts[0]
  const action = approvalAction(interrupt as unknown as InterruptLike)
  // The interrupt's own id, not a run id: LangGraph matches a resume answer to
  // the interrupt that raised it, and a thread can be paused on more than one.
  const interruptId = String(interrupt.id ?? "interrupt:0")
  const toolCallId = action.toolCallId ?? interruptId
  const metadata = {
    custom: { agui: { interrupts: [{
      id: interruptId,
      reason: "approval",
      toolCallId,
      metadata: {
        actionId: toolCallId,
        tool: action.tool,
        targets: action.targets,
      },
    }] } },
    unstable_state: null,
    unstable_annotations: [],
    unstable_data: [],
    steps: [],
    submittedFeedback: undefined,
    timing: undefined,
  }
  messages.push({
    id: `${interruptId}-approval`,
    role: "assistant",
    content: [],
    status: { type: "requires-action", reason: "interrupt" },
    createdAt: new Date(0),
    metadata,
  } as ThreadMessage)
  return messages
}
