"use client"

import {
  AuiIf,
  AttachmentPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react"
import { useAgUiInterrupts, useAgUiSubmitInterruptResponses } from "@assistant-ui/react-ag-ui"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { approvalAction } from "@/lib/assistant/approval-action"
import { PaperPlaneRightIcon, PlusIcon, XIcon } from "@/lib/icons"

import { ApprovalRequestCard, type ApprovalRequest } from "./approval-request-card"
import { useAssistantRuntimeProblem } from "./assistant-runtime-bridge"
import { CreditMeter } from "./credit-meter"
import { ModelSelector } from "./model-selector"

function ToolView({ toolName, args, result }: {
  toolName: string
  args: unknown
  result: unknown
}) {
  return (
    <section aria-label={`Tool ${toolName}`} className="rounded-md border bg-muted/30 p-2 text-xs">
      <p className="font-medium">{toolName.replaceAll("_", " ")}</p>
      <p className="text-muted-foreground">Arguments</p>
      <pre className="overflow-auto whitespace-pre-wrap">{JSON.stringify(args ?? {}, null, 2)}</pre>
      {result === undefined ? (
        <p role="status">Running tool…</p>
      ) : (
        <>
          <p className="text-muted-foreground">Result</p>
          <pre className="overflow-auto whitespace-pre-wrap">{typeof result === "string" ? result : JSON.stringify(result, null, 2)}</pre>
        </>
      )}
    </section>
  )
}

function ChatMessage() {
  const role = useAuiState((state) => state.message.role)
  return (
    <MessagePrimitive.Root className={role === "user" ? "ml-auto max-w-[90%] rounded-xl bg-muted px-3 py-2 text-sm" : "max-w-full py-2 text-sm"}>
      <MessagePrimitive.Parts>
        {({ part }) => {
          if (part.type === "text") return <p className="whitespace-pre-wrap">{part.text}</p>
          if (part.type === "tool-call") return <ToolView toolName={part.toolName} args={part.args} result={part.result} />
          return null
        }}
      </MessagePrimitive.Parts>
      <MessagePrimitive.Attachments>
        {() => <ImageAttachment />}
      </MessagePrimitive.Attachments>
    </MessagePrimitive.Root>
  )
}

function ImageAttachment({ removable = false }: { removable?: boolean }) {
  return (
    <AttachmentPrimitive.Root className="relative mt-2 flex max-w-40 items-center gap-2 rounded-md border p-1">
      <AttachmentPrimitive.unstable_Thumb className="size-16 rounded object-cover" />
      <span className="min-w-0 truncate text-xs"><AttachmentPrimitive.Name /></span>
      {removable ? (
        <AttachmentPrimitive.Remove aria-label="Remove image" className="rounded p-1 hover:bg-muted">
          <XIcon className="size-4" />
        </AttachmentPrimitive.Remove>
      ) : null}
    </AttachmentPrimitive.Root>
  )
}

function ApprovalGate() {
  const interrupts = useAgUiInterrupts()
  const submit = useAgUiSubmitInterruptResponses()
  const [problem, setProblem] = useState<string | null>(null)
  return <>
    {interrupts.map((interrupt) => {
      const action = approvalAction(interrupt)
      const approval: ApprovalRequest = {
        key: interrupt.id,
        runId: interrupt.id,
        actionId: action.toolCallId ?? interrupt.id,
        tool: action.tool,
        targets: action.targets,
      }
      return <ApprovalRequestCard key={interrupt.id} approval={approval} onDecide={async (_runId, _actionId, decision) => {
        setProblem(null)
        try {
          await submit([{ interruptId: interrupt.id, status: "resolved", payload: { decision } }])
        } catch (error) {
          setProblem(error instanceof Error ? error.message : "Could not submit decision")
          throw error
        }
      }} />
    })}
    {problem ? <p role="alert" className="text-sm text-destructive">{problem}</p> : null}
  </>
}

export function AssistantChat() {
  const interrupts = useAgUiInterrupts()
  const attachmentCount = useAuiState((state) => state.composer.attachments.length)
  const problem = useAssistantRuntimeProblem()
  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col gap-2">
      <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-2" aria-label="Assistant conversation">
        <AuiIf condition={(state) => state.thread.isEmpty}>
          <Empty className="border-none">
            <EmptyHeader>
              <EmptyTitle>Ask about your library</EmptyTitle>
              <EmptyDescription>Find words, build decks, or organise folders. Sensitive changes ask you first.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        </AuiIf>
        <ThreadPrimitive.Messages components={{ Message: ChatMessage }} />
        <ThreadPrimitive.ViewportFooter />
      </ThreadPrimitive.Viewport>
      <ApprovalGate />
      {problem ? <p role="alert" className="text-sm text-destructive">{problem}</p> : null}
      <ComposerPrimitive.Root className="flex flex-col gap-2 rounded-lg border p-2">
        <ComposerPrimitive.Attachments>
          {() => <ImageAttachment removable />}
        </ComposerPrimitive.Attachments>
        <div className="flex items-center gap-1">
          {/* Disabled while a run is paused: the model is snapshotted for that run,
              so offering a change the server would refuse is worse than hiding it. */}
          {interrupts.length === 0 ? (
            <>
              <ModelSelector />
              <CreditMeter />
            </>
          ) : null}
        </div>
        <div className="flex items-end gap-2">
          {attachmentCount === 0 ? (
            <ComposerPrimitive.AddAttachment aria-label="Attach image" className="rounded p-2 hover:bg-muted" disabled={interrupts.length > 0}>
              <PlusIcon className="size-4" />
            </ComposerPrimitive.AddAttachment>
          ) : null}
        <ComposerPrimitive.Input
          aria-label="Message the assistant"
          placeholder={interrupts.length ? "Answer the request above to continue" : "Ask about your library"}
          disabled={interrupts.length > 0}
          maxLength={8000}
          rows={2}
          className="min-h-10 flex-1 resize-none bg-transparent text-sm outline-none"
        />
        <ComposerPrimitive.Send asChild>
          <Button size="icon-sm" aria-label="Send" disabled={interrupts.length > 0}>
            <PaperPlaneRightIcon />
          </Button>
        </ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </ThreadPrimitive.Root>
  )
}
