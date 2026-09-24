import { describe, expect, test } from "vitest"

import { createAssistantStore } from "@/lib/stores/assistant-store"
import type { ModelCatalog } from "@/lib/api/types"

const catalog: ModelCatalog = {
  defaultModel: "reasoning-model",
  defaultReasoningEffort: "medium",
  models: [
    {
      id: "reasoning-model",
      name: "Reasoning Model",
      provider: "test",
      vision: true,
      reasoning: true,
      supportedEfforts: ["none", "low", "medium", "high"],
      contextWindow: 1000,
      maxOutputTokens: 100,
      pricing: { inputUsdPerM: 1, outputUsdPerM: 2, cachedReadUsdPerM: 0.1 },
      isDefault: true,
    },
    {
      id: "plain-model",
      name: "Plain Model",
      provider: "test",
      vision: false,
      reasoning: false,
      supportedEfforts: ["none"],
      contextWindow: 1000,
      maxOutputTokens: 100,
      pricing: { inputUsdPerM: 1, outputUsdPerM: 2, cachedReadUsdPerM: 0.1 },
      isDefault: false,
    },
  ],
}

describe("assistant model selection", () => {
  test("the catalog seeds the selection from the server's default", () => {
    const store = createAssistantStore()

    store.getState().setCatalog(catalog)

    expect(store.getState().selectedModel).toBe("reasoning-model")
    expect(store.getState().selectedEffort).toBe("medium")
  })

  test("switching to a model without the current effort coerces it", () => {
    const store = createAssistantStore()
    store.getState().setCatalog(catalog)

    store.getState().selectModel("plain-model")

    // Sending "medium" to a model that does not support it is a server 4xx, so
    // the value is coerced rather than carried over.
    expect(store.getState().selectedModel).toBe("plain-model")
    expect(store.getState().selectedEffort).toBe("none")
  })

  test("switching to a model that supports the current effort keeps it", () => {
    const store = createAssistantStore()
    store.getState().setCatalog(catalog)
    store.getState().selectModel("plain-model")
    store.getState().selectModel("reasoning-model")

    expect(store.getState().selectedEffort).toBe("none")
  })

  test("an unknown model id is ignored rather than stored", () => {
    const store = createAssistantStore()
    store.getState().setCatalog(catalog)

    store.getState().selectModel("not-in-the-catalog")

    expect(store.getState().selectedModel).toBe("reasoning-model")
  })
})
