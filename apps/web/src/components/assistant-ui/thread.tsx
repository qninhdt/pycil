"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActionBarPrimitive,
  AuiIf,
  AttachmentPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAui,
  useAuiState,
  type ReasoningMessagePartComponent,
  type ToolCallMessagePartComponent,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkMath from "remark-math";
import remarkMathjaxDelimiters from "remark-mathjax-delimiters";
import rehypeKatex from "rehype-katex";
import { Icon } from "@/components/artwork/artwork";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ModelLogo } from "./model-logo";
import type { AssistantModel, ReasoningEffort } from "@/lib/assistant-api";

export function AssistantGeometry() {
  return (
    <svg viewBox="0 0 160 104" className="ai-geometry" aria-hidden="true">
      <path d="M8 79h144M91 8v88" stroke="var(--foreground)" />
      <circle cx="51" cy="43" r="30" fill="var(--art-red)" />
      <rect x="91" y="47" width="32" height="32" fill="var(--art-blue)" />
      <path d="m126 12 28 35H98Z" fill="var(--art-yellow)" />
    </svg>
  );
}

export const Reasoning: ReasoningMessagePartComponent = ({ status }) => (
  <details className="ai-reasoning" open={status.type === "running"}>
    <summary>
      <Icon name="layers" tone="color" />
      <span>{status.type === "running" ? "Thinking…" : "Reasoning"}</span>
      <Icon name="chevron-down" variant="control" />
    </summary>
    <div className="ai-reasoning-body">
      <Markdown />
    </div>
  </details>
);

const toolLabels: Record<string, string> = {
  search_words: "Searching the Dictionary",
  list_nodes: "Reading your Library",
  get_node: "Opening Library content",
  get_node_editor: "Reading deck details",
  learning_progress: "Checking learning progress",
  create_node: "Create Library content",
  update_node: "Update Library content",
  delete_node: "Delete Library content",
};
export const ToolResult: ToolCallMessagePartComponent = ({
  toolName,
  args,
  result,
  status,
  isError,
}) => (
  <details className="ai-tool">
    <summary>
      <Icon name="folder" variant="control" tone="color" />
      <span>{toolLabels[toolName] ?? toolName.replaceAll("_", " ")}</span>
      <span className="ai-tool-status">
        {isError
          ? "Failed"
          : status.type === "running"
            ? "Working"
            : result !== undefined
              ? "Done"
              : "Review"}
      </span>
      <Icon name="chevron-down" variant="control" />
    </summary>
    <div className="ai-tool-body">
      <pre>{JSON.stringify(args, null, 2)}</pre>
      {result !== undefined && (
        <pre>
          {typeof result === "string"
            ? result
            : JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  </details>
);

function Attachment({ removable = false }: { removable?: boolean }) {
  const attachment = useAuiState((s) => s.attachment);
  const [preview, setPreview] = useState<string>();
  useEffect(() => {
    if (!attachment.file || !attachment.file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => setPreview(String(reader.result));
    reader.readAsDataURL(attachment.file);
    return () => {
      reader.onload = null;
      reader.abort();
    };
  }, [attachment.file]);
  const image = attachment.content?.find((part) => part.type === "image");
  const src =
    preview ??
    (image?.type === "image" &&
    /^(data:image\/(png|jpeg|webp);base64,|blob:)/.test(image.image)
      ? image.image
      : undefined);
  return (
    <AttachmentPrimitive.Root className="ai-attachment">
      {src ? (
        <img src={src} alt={attachment.name} />
      ) : (
        <Icon name="image" variant="control" tone="color" />
      )}
      <span>
        <AttachmentPrimitive.Name />
        {attachment.status.type === "running" && (
          <small>Preparing image…</small>
        )}
        {attachment.status.type === "incomplete" && (
          <small role="alert">
            Image unavailable. Remove it and try again.
          </small>
        )}
      </span>
      {removable && (
        <AttachmentPrimitive.Remove asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove ${attachment.name}`}
          >
            <Icon name="x" variant="control" />
          </Button>
        </AttachmentPrimitive.Remove>
      )}
    </AttachmentPrimitive.Root>
  );
}
function ComposerAttachment() {
  return <Attachment removable />;
}
function MessageAttachment() {
  return <Attachment />;
}
function Markdown() {
  return (
    <MarkdownTextPrimitive
      className="ai-markdown"
      remarkPlugins={[remarkMath, remarkMathjaxDelimiters]}
      rehypePlugins={[rehypeKatex]}
    />
  );
}

export function UserMessage() {
  return (
    <MessagePrimitive.Root className="ai-message ai-message-user">
      <div className="ai-message-content">
        <MessagePrimitive.Attachments
          components={{ Attachment: MessageAttachment }}
        />
        <MessagePrimitive.Parts components={{ Text: Markdown }} />
      </div>
    </MessagePrimitive.Root>
  );
}
export function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="ai-message ai-message-assistant">
      <div className="ai-message-content">
        <MessagePrimitive.Parts
          components={{
            Text: Markdown,
            Reasoning,
            tools: { Fallback: ToolResult },
          }}
        />
        <MessagePrimitive.Error>
          <p className="ai-message-error" role="alert">
            The response was interrupted. Reopen this conversation to check what
            was saved.
          </p>
        </MessagePrimitive.Error>
      </div>
      <AuiIf
        condition={(s) =>
          s.message.parts.some(
            (part) => part.type === "text" && part.text.trim().length > 0,
          )
        }
      >
        <ActionBarPrimitive.Root className="ai-message-actions">
          <ActionBarPrimitive.Copy asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Copy response">
              <Icon name="copy" variant="control" />
            </Button>
          </ActionBarPrimitive.Copy>
        </ActionBarPrimitive.Root>
      </AuiIf>
    </MessagePrimitive.Root>
  );
}

const REASONING_STEPS: readonly ReasoningEffort[] = [
  "low",
  "medium",
  "high",
] as const;

function formatEffort(value: string): string {
  if (value === "low") return "Low";
  if (value === "medium") return "Medium";
  if (value === "high") return "High";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function ReasoningEffortSlider({
  steps,
  currentStep,
  onEffort,
}: {
  steps: readonly ReasoningEffort[];
  currentStep: ReasoningEffort;
  onEffort: (effort: string) => void;
}) {
  const currentIndex = steps.indexOf(currentStep);
  const trackRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef(false);

  const updateStepFromClientX = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track) return;
      const rect = track.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = Math.max(
        0,
        Math.min(1, (clientX - rect.left) / rect.width),
      );
      const stepIndex = Math.min(
        steps.length - 1,
        Math.max(0, Math.round(ratio * (steps.length - 1))),
      );
      const targetStep = steps[stepIndex];
      if (targetStep && targetStep !== currentStep) {
        onEffort(targetStep);
      }
    },
    [steps, currentStep, onEffort],
  );

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    isDraggingRef.current = true;
    updateStepFromClientX(e.clientX);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    updateStepFromClientX(e.clientX);
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isDraggingRef.current) {
      isDraggingRef.current = false;
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {}
    }
  };

  const activePercent = (currentIndex / (steps.length - 1)) * 100;

  return (
    <div className="ai-effort-slider-wrap">
      <div
        ref={trackRef}
        className="ai-effort-track"
        role="slider"
        aria-label="Thinking effort"
        aria-valuemin={0}
        aria-valuemax={steps.length - 1}
        aria-valuenow={currentIndex}
        aria-valuetext={formatEffort(currentStep)}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" || e.key === "ArrowUp") {
            e.preventDefault();
            if (currentIndex < steps.length - 1)
              onEffort(steps[currentIndex + 1]);
          } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
            e.preventDefault();
            if (currentIndex > 0) onEffort(steps[currentIndex - 1]);
          }
        }}
      >
        <div
          className="ai-effort-fill"
          style={{ width: `${activePercent}%` }}
        />
        {steps.map((step, idx) => (
          <span
            key={step}
            className="ai-effort-dot"
            style={{ left: `${(idx / (steps.length - 1)) * 100}%` }}
            data-active={idx <= currentIndex}
          />
        ))}
        <span
          className="ai-effort-thumb"
          style={{ left: `${activePercent}%` }}
          aria-hidden="true"
        />
      </div>

      <div className="ai-effort-labels">
        {steps.map((step, idx) => (
          <button
            type="button"
            key={step}
            className="ai-effort-label-btn"
            data-active={idx === currentIndex}
            onClick={() => onEffort(step)}
          >
            {formatEffort(step)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ModelPicker({
  models,
  model,
  effort,
  onModel,
  onEffort,
  disabled = false,
}: {
  models: AssistantModel[];
  model: AssistantModel;
  effort: string;
  onModel: (id: string) => void;
  onEffort: (effort: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [showModels, setShowModels] = useState(false);

  const steps: readonly ReasoningEffort[] = REASONING_STEPS;
  const currentStep = (
    steps.includes(effort as ReasoningEffort) ? effort : "medium"
  ) as ReasoningEffort;

  return (
    <Popover
      open={open}
      onOpenChange={(isOpen) => {
        setOpen(isOpen);
        if (!isOpen) setShowModels(false);
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          className="ai-model-trigger"
          disabled={disabled}
          aria-label="Choose model"
        >
          <ModelLogo modelId={model.id} modelName={model.name} />
          <span className="ai-model-name">{model.name}</span>
          <Icon name="chevron-down" variant="control" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" side="top" className="ai-model-popover">
        <div className="ai-model-section">
          <DropdownMenu open={showModels} onOpenChange={setShowModels}>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="ai-model-select-btn"
                aria-label="Select model"
              >
                <div className="ai-model-select-left">
                  <ModelLogo modelId={model.id} modelName={model.name} />
                  <span className="ai-model-select-name">{model.name}</span>
                </div>
                <Icon
                  name={showModels ? "chevron-up" : "chevron-down"}
                  variant="control"
                  className="size-3.5 opacity-60"
                />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className="ai-model-dropdown-list"
              style={{ width: "var(--radix-dropdown-menu-trigger-width)" }}
            >
              <DropdownMenuRadioGroup
                value={model.id}
                onValueChange={(id) => {
                  onModel(id);
                  setOpen(false);
                }}
              >
                {models.map((item) => (
                  <DropdownMenuRadioItem
                    key={item.id}
                    value={item.id}
                    className="ai-model-item"
                  >
                    <ModelLogo modelId={item.id} modelName={item.name} />
                    <span className="ai-model-item-name">{item.name}</span>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="ai-popover-divider" />

        <div className="ai-effort-section">
          <ReasoningEffortSlider
            steps={steps}
            currentStep={currentStep}
            onEffort={onEffort}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}

export const ModelMenu = ModelPicker;

export function AssistantThread({
  models,
  model,
  effort,
  onModel,
  onEffort,
  error,
  clearError,
  footer,
  usage,
}: {
  models: AssistantModel[];
  model: AssistantModel;
  effort: string;
  onModel: (id: string) => void;
  onEffort: (effort: string) => void;
  error?: string | null;
  clearError?: () => void;
  footer?: React.ReactNode;
  usage?: React.ReactNode;
}) {
  const aui = useAui();
  const running = useAuiState((s) => s.thread.isRunning);
  const attachmentCount = useAuiState((s) => s.composer.attachments.length);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const message = attachmentError ?? error;
  useEffect(
    () =>
      aui.on("composer.attachmentAdd", () => {
        setAttachmentError(null);
        clearError?.();
      }),
    [aui, clearError],
  );
  useEffect(
    () =>
      aui.on("composer.attachmentAddError", (event) =>
        setAttachmentError(event.message),
      ),
    [aui],
  );
  return (
    <ThreadPrimitive.Root className="ai-thread">
      <ThreadPrimitive.Viewport
        className="ai-viewport"
        aria-label="Conversation messages"
      >
        <ThreadPrimitive.Empty>
          <div className="ai-empty">
            <div className="ai-empty-badge">
              <Icon name="spark" tone="color" className="size-6" />
            </div>
            <h2>How can I help you today?</h2>
            <div className="ai-suggestions">
              {[
                {
                  title: "Summarize this page",
                  prompt: "Summarize the current page and key concepts",
                  icon: "list" as const,
                },
                {
                  title: "Translate this page",
                  prompt: "Translate and explain key words in context",
                  icon: "translate" as const,
                },
                {
                  title: "Analyze for insights",
                  prompt:
                    "Analyze my vocabulary retention and suggest improvements",
                  icon: "search" as const,
                },
                {
                  title: "Create a task tracker",
                  prompt: "Create a quick quiz for my recently studied cards",
                  icon: "circle-check" as const,
                },
              ].map((item) => (
                <ThreadPrimitive.Suggestion
                  key={item.title}
                  prompt={item.prompt}
                  method="replace"
                  autoSend={false}
                  className="ai-suggestion"
                >
                  {item.icon === "translate" ? (
                    <Icon name="translate" tone="color" />
                  ) : (
                    <Icon name={item.icon} variant="control" tone="color" />
                  )}
                  <span>{item.title}</span>
                  <Icon name="arrow-up-right" variant="control" />
                </ThreadPrimitive.Suggestion>
              ))}
            </div>
          </div>
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages
          components={{ UserMessage, AssistantMessage }}
        />
        {footer}
      </ThreadPrimitive.Viewport>
      <div className="ai-composer-wrap">
        <ThreadPrimitive.ScrollToBottom asChild>
          <Button
            variant="outline"
            size="icon-sm"
            className="ai-scroll-bottom"
            aria-label="Scroll to latest message"
          >
            <Icon name="arrow-down" variant="control" />
          </Button>
        </ThreadPrimitive.ScrollToBottom>
        {message && (
          <div className="ai-error" role="alert">
            <p>{message}</p>
            {(clearError || attachmentError) && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  setAttachmentError(null);
                  clearError?.();
                }}
                aria-label="Dismiss assistant error"
              >
                <Icon name="x" variant="control" />
              </Button>
            )}
          </div>
        )}
        {usage ?? (
          <div className="ai-plan-banner">
            Design preview · No AI allowance is consumed.
          </div>
        )}
        <ComposerPrimitive.Root className="ai-composer">
          <div className="ai-composer-attachments">
            <ComposerPrimitive.Attachments
              components={{ Attachment: ComposerAttachment }}
            />
          </div>
          <ComposerPrimitive.Input
            autoFocus
            aria-label="Message PycilAI"
            placeholder="Ask Pycil AI…"
            maxLength={8000}
            rows={2}
            className="ai-input"
          />
          <div className="ai-composer-toolbar">
            <ComposerPrimitive.AddAttachment asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Attach images"
                disabled={!model.vision || running || attachmentCount >= 4}
                title={
                  model.vision
                    ? "Attach images (PNG, JPEG, WebP)"
                    : "Choose a vision model to attach images"
                }
              >
                <Icon name="plus" variant="control" />
              </Button>
            </ComposerPrimitive.AddAttachment>
            <span className="ai-toolbar-spacer" />
            <ModelMenu
              models={models}
              model={model}
              effort={effort}
              onModel={onModel}
              onEffort={onEffort}
            />
            {running ? (
              <ComposerPrimitive.Cancel asChild>
                <Button
                  size="icon"
                  aria-label="Stop response"
                  className="ai-send"
                >
                  <Icon name="stop" variant="control" />
                </Button>
              </ComposerPrimitive.Cancel>
            ) : (
              <ComposerPrimitive.Send asChild>
                <Button
                  size="icon"
                  aria-label="Send message"
                  className="ai-send"
                >
                  <Icon name="arrow-up" variant="control" />
                </Button>
              </ComposerPrimitive.Send>
            )}
          </div>
        </ComposerPrimitive.Root>
      </div>
    </ThreadPrimitive.Root>
  );
}
