"use client"

/**
 * The model and reasoning controls for the next assistant turn.
 *
 * The catalog is the server's: this renders what it was offered and never
 * hard-codes an id or a price, so a model the gateway cannot run is never
 * selectable. A model that does not support reasoning hides the effort control
 * rather than offering a value the server would refuse.
 *
 * The selection applies to the next turn, not to the conversation: the server
 * snapshots the model and tariff each run actually used, so changing this cannot
 * re-price a turn that already happened.
 */

import { useEffect } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { getModelCatalog } from "@/lib/actions/assistant"
import { SparkleIcon } from "@/lib/icons"
import { useAssistantStore, useAssistantStoreApi } from "@/lib/stores/store-provider"

/** What each effort level means for the learner, not for the provider. */
const EFFORT_LABEL: Record<string, string> = {
  none: "Off",
  low: "Low",
  medium: "Medium",
  high: "High",
}

export function ModelSelector() {
  const store = useAssistantStoreApi()
  const catalog = useAssistantStore((state) => state.catalog)
  const selectedModel = useAssistantStore((state) => state.selectedModel)
  const selectedEffort = useAssistantStore((state) => state.selectedEffort)

  useEffect(() => {
    if (catalog) return
    void getModelCatalog().then((result) => {
      // A failed catalog read leaves the controls absent rather than showing an
      // invented default: the server picks the model when nothing is sent.
      if (result.success) store.getState().setCatalog(result.data)
    })
  }, [catalog, store])

  if (!catalog) return null

  const model = catalog.models.find((entry) => entry.id === selectedModel) ?? catalog.models[0]
  if (!model) return null

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="max-w-40 gap-1.5 text-xs text-muted-foreground"
              aria-label={`Model: ${model.name}`}
            />
          }
        >
          <SparkleIcon className="size-3.5" aria-hidden />
          <span className="truncate">{model.name}</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          <DropdownMenuLabel>Model</DropdownMenuLabel>
          <DropdownMenuGroup>
            {catalog.models.map((entry) => (
              <DropdownMenuItem
                key={entry.id}
                onClick={() => store.getState().selectModel(entry.id)}
                aria-current={entry.id === model.id ? "true" : undefined}
              >
                <span className="truncate">{entry.name}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <p className="px-2 py-1.5 text-xs text-muted-foreground">
            Applies to your next message.
          </p>
        </DropdownMenuContent>
      </DropdownMenu>

      {model.reasoning ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="sm"
                className="gap-1.5 text-xs text-muted-foreground"
                aria-label={`Reasoning: ${EFFORT_LABEL[selectedEffort ?? "none"] ?? selectedEffort}`}
              />
            }
          >
            <span>{EFFORT_LABEL[selectedEffort ?? "none"] ?? selectedEffort}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-40">
            <DropdownMenuLabel>Reasoning</DropdownMenuLabel>
            <DropdownMenuGroup>
              {model.supportedEfforts.map((effort) => (
                <DropdownMenuItem
                  key={effort}
                  onClick={() => store.getState().selectEffort(effort)}
                  aria-current={effort === selectedEffort ? "true" : undefined}
                >
                  {EFFORT_LABEL[effort] ?? effort}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </>
  )
}