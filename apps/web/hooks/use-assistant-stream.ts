"use client";

import { useCallback, useState } from "react";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actionPayload?: {
    actionId: string;
    description: string;
    warning?: string;
  };
}

export function useAssistantStream(threadId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!threadId || !content.trim() || isStreaming) return;

      setError(null);
      const userMsgId = `user-${Date.now()}`;
      const assistantMsgId = `asst-${Date.now()}`;

      setMessages((prev) => [
        ...prev,
        { id: userMsgId, role: "user", content },
        { id: assistantMsgId, role: "assistant", content: "" },
      ]);

      setIsStreaming(true);

      try {
        const response = await fetch(`/api/assistant/threads/${threadId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error("No response body stream");

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim() || line.startsWith(":")) continue;

            let eventName = "message";
            let dataStr = "";

            for (const subLine of line.split("\n")) {
              if (subLine.startsWith("event: ")) {
                eventName = subLine.slice(7).trim();
              } else if (subLine.startsWith("data: ")) {
                dataStr = subLine.slice(6).trim();
              }
            }

            if (!dataStr) continue;

            try {
              const data = JSON.parse(dataStr);
              if (eventName === "token" && data.text) {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: msg.content + data.text }
                      : msg
                  )
                );
              } else if (eventName === "action") {
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          actionPayload: {
                            actionId: data.actionId || data.id,
                            description: data.description || "Action confirmation requested",
                            warning: data.warning,
                          },
                        }
                      : msg
                  )
                );
              } else if (eventName === "error") {
                setError(data.message || "An error occurred during streaming");
              }
            } catch (e) {
              console.warn("Failed to parse SSE frame", e);
            }
          }
        }
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "Failed to connect to assistant stream";
        setError(errorMsg);
      } finally {
        setIsStreaming(false);
      }
    },
    [threadId, isStreaming]
  );

  return {
    messages,
    setMessages,
    isStreaming,
    error,
    sendMessage,
  };
}
