"use client";

import { MessageSquare, Plus, Trash2 } from "lucide-react";
import type { AssistantThread } from "@/lib/api/types";

interface ThreadSidebarProps {
  threads: AssistantThread[];
  activeThreadId: string | null;
  onSelectThread: (id: string) => void;
  onNewThread: () => void;
  onDeleteThread: (id: string) => void;
}

export function ThreadSidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
}: ThreadSidebarProps) {
  return (
    <div className="w-full md:w-64 border-r border-neutral-200 dark:border-neutral-800 flex flex-col h-full bg-neutral-50/50 dark:bg-neutral-900/50">
      <div className="p-4 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between">
        <h3 className="font-semibold text-sm text-neutral-900 dark:text-neutral-100">
          AI Conversations
        </h3>
        <button
          type="button"
          onClick={onNewThread}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {threads.length === 0 ? (
          <p className="p-4 text-xs text-neutral-400 text-center">No active chats yet</p>
        ) : (
          threads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            return (
              <div
                key={thread.id}
                onClick={() => onSelectThread(thread.id)}
                className={`group flex items-center justify-between p-2.5 rounded-xl cursor-pointer text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-blue-100/70 text-blue-900 dark:bg-blue-950/60 dark:text-blue-200"
                    : "text-neutral-700 dark:text-neutral-300 hover:bg-neutral-200/50 dark:hover:bg-neutral-800"
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <MessageSquare className="w-4 h-4 shrink-0 text-neutral-400" />
                  <span className="truncate">{thread.title || "Untitled Conversation"}</span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(thread.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 dark:hover:bg-red-950 text-neutral-400 hover:text-red-600 transition-all"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
