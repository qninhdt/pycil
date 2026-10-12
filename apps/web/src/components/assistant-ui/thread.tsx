"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActionBarPrimitive,
  AuiIf,
  AttachmentPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  ReadonlyThreadProvider,
  useAui,
  useAuiState,
  type ReasoningMessagePartComponent,
  type ToolCallMessagePartComponent,
  type ThreadMessage,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import remarkMath from "remark-math";
import remarkMathjaxDelimiters from "remark-mathjax-delimiters";
import rehypeKatex from "rehype-katex";
import { useTranslations } from "next-intl";
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
import { cn } from "@/lib/utils";
import { ModelLogo } from "./model-logo";
import { ToolBodyContent, getToolPreview, toolTitles } from "./tool-renderers";
import { AssistantContextTab } from "./assistant-context";
import type { AssistantModel, ReasoningEffort } from "@/lib/assistant-api";
import { mergeAssistantTurns } from "@/lib/assistant-messages";

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

export const Reasoning: ReasoningMessagePartComponent = ({ status }) => {
  const t = useTranslations("assistant");
  const isRunning = status.type === "running";
  return (
    <details className="ai-reasoning" open={isRunning}>
      <summary>
        <Icon name="layers" tone="color" />
        <span className={cn(isRunning && "shimmer text-foreground/70")}>{isRunning ? t("thinking") : t("reasoning")}</span>
        <Icon name="chevron-down" variant="control" />
      </summary>
      <div className="ai-reasoning-body">
        <Markdown />
      </div>
    </details>
  );
};

function Attachment({ removable = false }: { removable?: boolean }) {
  const attachment = useAuiState((s) => s.attachment);
  return <AttachmentView attachment={attachment} removable={removable} />;
}

function AttachmentView({ attachment, removable = false }: { attachment: import('@assistant-ui/react').Attachment; removable?: boolean }) {
  const t = useTranslations("assistant");
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
    <div className="ai-attachment">
      {src ? (
        <img src={src} alt={attachment.name} />
      ) : (
        <Icon name="image" variant="control" tone="color" />
      )}
      <span>
        <span>{attachment.name}</span>
        {attachment.status.type === "running" && (
          <small>{t("preparingImage")}</small>
        )}
        {attachment.status.type === "incomplete" && (
          <small role="alert">
            {t("imageUnavailable")}
          </small>
        )}
      </span>
      {removable && (
        <AttachmentPrimitive.Remove asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("removeAttachmentAria", { name: attachment.name })}
          >
            <Icon name="x" variant="control" />
          </Button>
        </AttachmentPrimitive.Remove>
      )}
    </div>
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
  const submission = useAuiState((s) => s.message.submission);
  return (
    <MessagePrimitive.Root className="ai-message ai-message-user">
      <div className="ai-message-content">
        {submission ? submission.attachments.map(attachment => <AttachmentView key={attachment.id} attachment={attachment} />)
          : <MessagePrimitive.Attachments components={{ Attachment: MessageAttachment }} />}
        <MessagePrimitive.Parts components={{ Text: Markdown }} />
      </div>
    </MessagePrimitive.Root>
  );
}
function TimelineReasoningPart() {
  return (
    <div className="ai-timeline-item ai-timeline-item-reasoning">
      <div className="ai-timeline-content">
        <Markdown />
      </div>
    </div>
  );
}

function TimelineToolPart({ part }: { part: any }) {
  const t = useTranslations("assistant");
  const [isOpen, setIsOpen] = useState(false);
  const meta = toolTitles[part.toolName] ?? {
    title: part.toolName.replace(/_/g, " "),
    icon: "folder",
    tone: "color",
  };
  const isRunning = part.status?.type === "running";
  const preview = getToolPreview(part.toolName, part.args, part.result);

  return (
    <div className="ai-timeline-item ai-timeline-item-tool">
      <div className="ai-timeline-content w-full">
        <details className="ai-tool" open={isOpen || isRunning}>
          <summary
            className="ai-tool-summary w-full text-left cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden"
            onClick={(e) => {
              e.preventDefault();
              setIsOpen(!isOpen);
            }}
            aria-expanded={isOpen || isRunning}
          >
            <Icon
              name={meta.icon as any}
              variant="control"
              tone={meta.tone as any}
              className="size-4 shrink-0"
            />
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="ai-tool-title">{meta.title}</span>
              {preview && (
                <span className="ai-tool-preview font-mono text-[11px] text-muted-foreground truncate max-w-[180px] hidden sm:inline">
                  {preview}
                </span>
              )}
            </div>
            {isRunning && (
              <span className="ai-tool-status shimmer text-foreground/80 font-medium" data-running="true">
                {t("working")}
              </span>
            )}
            {part.isError && (
              <span className="ai-tool-status" data-error="true">
                {t("failed")}
              </span>
            )}
            <Icon
              name="chevron-down"
              variant="control"
              className="size-3.5 opacity-60 ml-auto transition-transform"
            />
          </summary>
          {(isOpen || isRunning) && (
            <div className="ai-tool-body">
              <ToolBodyContent
                toolName={part.toolName}
                args={part.args}
                result={part.result}
                status={part.status ?? { type: "complete" }}
                isError={part.isError}
                meta={meta}
              />
            </div>
          )}
        </details>
      </div>
    </div>
  );
}

const TimelineTool: ToolCallMessagePartComponent = (part) => <TimelineToolPart part={part} />;

function ThoughtProcessContainer({
  children,
}: {
  children: React.ReactNode;
}) {
  const message = useAuiState((s) => s.message);
  const status = useAuiState((s) => s.message.status);

  // Check if this message already has started receiving text tokens
  const hasText = message.parts.some(
    (p) => p.type === "text" && Boolean(p.text && p.text.trim().length > 0),
  );
  const isRunning = status?.type === "running";

  // If text already exists (e.g. completed message/history), start collapsed.
  // If streaming tools/reasoning without text yet, start open.
  const [isOpen, setIsOpen] = useState(!hasText);

  const prevHasTextRef = useRef(hasText);
  const prevRunningRef = useRef(isRunning);

  useEffect(() => {
    // When text begins streaming (transition from no text -> has text), auto-collapse thought!
    if (!prevHasTextRef.current && hasText) {
      setIsOpen(false);
    }
    // When starting a new run that has no text yet (streaming tools/reasoning), auto-expand thought!
    else if (!prevRunningRef.current && isRunning && !hasText) {
      setIsOpen(true);
    }
    // When turn completes and has text, ensure thought is collapsed
    else if (prevRunningRef.current && !isRunning && hasText) {
      setIsOpen(false);
    }

    prevHasTextRef.current = hasText;
    prevRunningRef.current = isRunning;
  }, [isRunning, hasText]);

  const t = useTranslations("assistant");
  const title = isRunning ? t("thinking") : t("thought");

  return (
    <details
      className="ai-reasoning"
      open={isOpen}
      onToggle={(e) => {
        setIsOpen((e.currentTarget as HTMLDetailsElement).open);
      }}
    >
      <summary className="ai-reasoning-summary">
        <Icon name="layers" tone="color" className="size-3.5 shrink-0" />
        <span className={cn("ai-reasoning-label", isRunning && "shimmer text-foreground/70")}>{title}</span>
        {isRunning && (
          <span className="inline-block size-1.5 bg-[var(--art-blue)] shimmer ml-1" />
        )}
        <Icon
          name="chevron-down"
          variant="control"
          className="size-3.5 shrink-0 ml-auto transition-transform"
        />
      </summary>
      <div className="ai-reasoning-body">
        <div className="ai-timeline">{children}</div>
      </div>
    </details>
  );
}

export function AssistantMessage() {
  const t = useTranslations("assistant");
  const hasThought = useAuiState((s) =>
    s.message.parts.some((p) => p.type === "reasoning" || p.type === "tool-call"),
  );
  const parts = useAuiState((s) => s.message.parts);

  return (
    <MessagePrimitive.Root className="ai-message ai-message-assistant">
      <div className="ai-message-content">
        {hasThought ? (
          <>
            <ThoughtProcessContainer>
              {parts.map((part, index) => (part.type === "reasoning" || part.type === "tool-call") &&
                <MessagePrimitive.PartByIndex key={index} index={index}
                  components={{ Reasoning: TimelineReasoningPart, tools: { Fallback: TimelineTool } }} />)}
            </ThoughtProcessContainer>
            {parts.map((part, index) => part.type !== "reasoning" && part.type !== "tool-call" &&
              <MessagePrimitive.PartByIndex key={index} index={index} components={{ Text: Markdown }} />)}
          </>
        ) : (
          <MessagePrimitive.Parts components={{ Text: Markdown }} />
        )}
        <MessagePrimitive.Error>
          <p className="ai-message-error" role="alert">
            {t("responseInterrupted")}
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
            <Button variant="ghost" size="icon-sm" aria-label={t("copyResponseAria")}>
              <Icon name="copy" variant="control" />
            </Button>
          </ActionBarPrimitive.Copy>
        </ActionBarPrimitive.Root>
      </AuiIf>
    </MessagePrimitive.Root>
  );
}

function TurnMessages({ snapshot }: { snapshot?: readonly ThreadMessage[] }) {
  const messages = useAuiState((s) => s.thread.messages);
  const turns = useMemo(() => mergeAssistantTurns(messages, snapshot), [messages, snapshot]);
  return <ReadonlyThreadProvider messages={turns}>
    <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
  </ReadonlyThreadProvider>;
}

const REASONING_STEPS: readonly ReasoningEffort[] = [
  "low",
  "medium",
  "high",
] as const;

function formatEffort(value: string, t: (key: any) => string): string {
  if (value === "low") return t("effortLow");
  if (value === "medium") return t("effortMedium");
  if (value === "high") return t("effortHigh");
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
  const t = useTranslations("assistant");
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
        aria-label={t("thinkingEffortAria")}
        aria-valuemin={0}
        aria-valuemax={steps.length - 1}
        aria-valuenow={currentIndex}
        aria-valuetext={formatEffort(currentStep, t)}
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
            {formatEffort(step, t)}
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
  const t = useTranslations("assistant");
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
          aria-label={t("chooseModelAria")}
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
                aria-label={t("selectModelAria")}
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
  snapshot,
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
  snapshot?: readonly ThreadMessage[];
}) {
  const t = useTranslations("assistant");
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

  const [isDragging, setIsDragging] = useState(false);
  const dragCounterRef = useRef(0);

  const handleDragEnter = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) {
      setIsDragging(true);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = model.vision && attachmentCount < 4 ? "copy" : "none";
  };

  const handleDragLeave = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragCounterRef.current = 0;
    setIsDragging(false);

    if (running) return;

    if (!model.vision) {
      setAttachmentError(t("chooseVisionModelPrompt"));
      return;
    }

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    const imageFiles = files.filter(
      (f) => f.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(f.name)
    );
    if (imageFiles.length === 0) {
      setAttachmentError(t("imageFormatNotice"));
      return;
    }

    if (attachmentCount + imageFiles.length > 4) {
      setAttachmentError(t("maxImagesNotice"));
      return;
    }

    for (const file of imageFiles) {
      try {
        await aui.composer.addAttachment(file);
      } catch (err) {
        setAttachmentError(err instanceof Error ? err.message : t("failedToAddImage"));
      }
    }
  };

  return (
    <ThreadPrimitive.Root
      className="ai-thread"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="ai-drop-overlay">
          <div className="ai-drop-overlay-badge">
            <Icon name="image" variant="control" tone="color" className="size-6" />
          </div>
          <p className="ai-drop-overlay-title">{t("dropImagesTitle")}</p>
          <p className="ai-drop-overlay-sub">
            {model.vision
              ? t("dropImagesSubVision")
              : t("dropImagesSubNoVision")}
          </p>
        </div>
      )}
      <ThreadPrimitive.Viewport
        className="ai-viewport"
        aria-label={t("conversationMessagesAria")}
      >
        <ThreadPrimitive.Empty>
          <div className="ai-empty">
            <div className="ai-empty-badge">
              <Icon name="spark" tone="color" className="size-6" />
            </div>
            <h2>{t("howCanIHelp")}</h2>
            <div className="ai-suggestions">
              {[
                {
                  title: t("suggestionSummarize"),
                  prompt: t("suggestionSummarizePrompt"),
                  icon: "list" as const,
                },
                {
                  title: t("suggestionTranslate"),
                  prompt: t("suggestionTranslatePrompt"),
                  icon: "translate" as const,
                },
                {
                  title: t("suggestionAnalyze"),
                  prompt: t("suggestionAnalyzePrompt"),
                  icon: "search" as const,
                },
                {
                  title: t("suggestionQuiz"),
                  prompt: t("suggestionQuizPrompt"),
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
        <TurnMessages snapshot={snapshot} />
        {footer}
      </ThreadPrimitive.Viewport>
      <div className="ai-composer-wrap">
        <ThreadPrimitive.ScrollToBottom asChild>
          <Button
            variant="outline"
            size="icon-sm"
            className="ai-scroll-bottom"
            aria-label={t("scrollToBottomAria")}
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
                aria-label={t("dismissErrorAria")}
              >
                <Icon name="x" variant="control" />
              </Button>
            )}
          </div>
        )}
        {usage}
        <AssistantContextTab />
        <ComposerPrimitive.Root className="ai-composer">
          <div className="ai-composer-attachments">
            <ComposerPrimitive.Attachments
              components={{ Attachment: ComposerAttachment }}
            />
          </div>
          <ComposerPrimitive.Input
            autoFocus
            aria-label={t("messagePycilAiAria")}
            placeholder={t("askPycilAiPlaceholder")}
            maxLength={8000}
            rows={2}
            className="ai-input"
          />
          <div className="ai-composer-toolbar">
            <ComposerPrimitive.AddAttachment asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("attachImagesAria")}
                disabled={!model.vision || running || attachmentCount >= 4}
                title={
                  model.vision
                    ? t("attachImagesTitleVision")
                    : t("attachImagesTitleNoVision")
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
                  aria-label={t("stopResponseAria")}
                  className="ai-send"
                >
                  <Icon name="stop" variant="control" />
                </Button>
              </ComposerPrimitive.Cancel>
            ) : (
              <ComposerPrimitive.Send asChild>
                <Button
                  size="icon"
                  aria-label={t("sendMessageAria")}
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
