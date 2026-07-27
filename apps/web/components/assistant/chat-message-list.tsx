"use client";

import { Bot, User as UserIcon } from "lucide-react";
import type { ChatMessage } from "@/hooks/use-assistant-stream";
import { HitlActionCard } from "./hitl-action-card";

interface ChatMessageListProps {
  threadId: string;
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
}

export function ChatMessageList({
  threadId,
  messages,
  isStreaming,
  error,
}: ChatMessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="p-4 rounded-2xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 mb-3">
          <Bot className="w-8 h-8" />
        </div>
        <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
          How can I help with your vocabulary today?
        </h3>
        <p className="mt-1 text-sm text-neutral-500 max-w-sm">
          Ask questions about word definitions, CEFR levels, example sentences, or ask me to manage your vocabulary decks.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
      {messages.map((msg) => {
        const isUser = msg.role === "user";
        return (
          <div
            key={msg.id}
            className={`flex gap-3 max-w-3xl ${isUser ? "ml-auto flex-row-reverse" : "mr-auto"}`}
          >
            <div
              className={`p-2 rounded-xl h-9 w-9 flex items-center justify-center shrink-0 text-sm font-semibold ${
                isUser
                  ? "bg-blue-600 text-white"
                  : "bg-neutral-200 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300"
              }`}
            >
              {isUser ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
            </div>

            <div className="space-y-2 max-w-prose">
              <div
                className={`p-4 rounded-2xl text-sm leading-relaxed ${
                  isUser
                    ? "bg-blue-600 text-white rounded-tr-none"
                    : "bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-tl-none shadow-xs"
                }`}
              >
                {msg.content || (isStreaming && !isUser ? "..." : "")}
              </div>

              {msg.actionPayload && (
                <HitlActionCard
                  threadId={threadId}
                  actionId={msg.actionPayload.actionId}
                  description={msg.actionPayload.description}
                  warning={msg.actionPayload.warning}
                />
              )}
            </div>
          </div>
        );
      })}

      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}
