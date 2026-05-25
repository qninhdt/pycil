"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send } from "lucide-react";

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

interface ChatPanelProps {
  sessionId: string;
}

export function ChatPanel({ sessionId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [streaming, setStreaming] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const res = await fetch(`/api/core/chat/sessions/${sessionId}/messages`, {
        credentials: "include",
      });
      if (!cancelled && res.ok) {
        const data = (await res.json()) as { messages: ChatMessage[] };
        setMessages(data.messages);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, streaming]);

  const send = async () => {
    const content = input.trim();
    if (!content || busy) return;
    setBusy(true);
    setInput("");
    const optimistic: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const res = await fetch(
        `/api/core/chat/sessions/${sessionId}/messages`,
        {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ content }),
        }
      );
      if (!res.ok) throw new Error(`send_failed_${res.status}`);

      const ev = new EventSource(
        `/api/core/chat/sessions/${sessionId}/stream`
      );
      let buf = "";
      setStreaming("");
      ev.addEventListener("token", (e) => {
        try {
          const { token } = JSON.parse((e as MessageEvent).data);
          buf += token ?? "";
          setStreaming(buf);
        } catch {
          // ignore
        }
      });
      ev.addEventListener("done", () => {
        ev.close();
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: buf,
            created_at: new Date().toISOString(),
          },
        ]);
        setStreaming(null);
        setBusy(false);
      });
      ev.onerror = () => {
        ev.close();
        setStreaming(null);
        setBusy(false);
      };
    } catch {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((m) => (
          <div
            key={m.id}
            className={
              m.role === "user"
                ? "ml-auto max-w-[80%] rounded-lg bg-primary text-primary-foreground px-3 py-2 text-sm"
                : "mr-auto max-w-[80%] rounded-lg bg-muted px-3 py-2 text-sm"
            }
          >
            {m.content}
          </div>
        ))}
        {streaming !== null ? (
          <div className="mr-auto max-w-[80%] rounded-lg bg-muted px-3 py-2 text-sm opacity-80">
            {streaming || "…"}
          </div>
        ) : null}
      </div>
      <div className="border-t p-3 flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the tutor…"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          disabled={busy}
        />
        <Button onClick={send} disabled={!input.trim() || busy}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
