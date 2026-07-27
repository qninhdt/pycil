"use client";

import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import {
  createThreadAction,
  deleteThreadAction,
  listThreadsAction,
} from "@/lib/actions/assistant";
import type { AssistantThread } from "@/lib/api/types";
import { ChatMessageList } from "@/components/assistant/chat-message-list";
import { ThreadSidebar } from "@/components/assistant/thread-sidebar";
import { useAssistantStream } from "@/hooks/use-assistant-stream";

export default function AssistantPage() {
  const [threads, setThreads] = useState<AssistantThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [input, setInput] = useState("");

  const { messages, isStreaming, error, sendMessage } = useAssistantStream(activeThreadId);

  useEffect(() => {
    async function loadThreads() {
      const list = await listThreadsAction();
      setThreads(list);
      if (list.length > 0) {
        setActiveThreadId(list[0].id);
      }
    }
    loadThreads();
  }, []);

  async function handleNewThread() {
    const thread = await createThreadAction("New Chat");
    if (thread) {
      setThreads((prev) => [thread, ...prev]);
      setActiveThreadId(thread.id);
    }
  }

  async function handleDeleteThread(id: string) {
    const ok = await deleteThreadAction(id);
    if (ok) {
      setThreads((prev) => prev.filter((t) => t.id !== id));
      if (activeThreadId === id) {
        const remaining = threads.filter((t) => t.id !== id);
        setActiveThreadId(remaining.length > 0 ? remaining[0].id : null);
      }
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || !activeThreadId) return;
    sendMessage(input.trim());
    setInput("");
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-4rem)] overflow-hidden bg-white dark:bg-neutral-950">
      {/* Sidebar */}
      <ThreadSidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThreadId}
        onNewThread={handleNewThread}
        onDeleteThread={handleDeleteThread}
      />

      {/* Main Chat Interface */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        <ChatMessageList
          threadId={activeThreadId || ""}
          messages={messages}
          isStreaming={isStreaming}
          error={error}
        />

        {/* Input Form */}
        <form
          onSubmit={handleSubmit}
          className="p-4 border-t border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-950"
        >
          <div className="flex items-center gap-2 max-w-3xl mx-auto">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                activeThreadId
                  ? "Type your message to AI assistant..."
                  : "Create a new chat to begin..."
              }
              disabled={!activeThreadId || isStreaming}
              className="flex-1 px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900 text-sm focus:outline-hidden focus:ring-2 focus:ring-blue-500 transition-all disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!activeThreadId || !input.trim() || isStreaming}
              className="p-3 rounded-xl bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
