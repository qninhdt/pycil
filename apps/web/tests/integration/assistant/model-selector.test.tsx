import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"

import { ModelSelector } from "@/components/assistant/model-selector"
import { StoreProvider, useAssistantStore } from "@/lib/stores/store-provider"

import { server } from "../server"

/**
 * The model control, driven through the endpoint it really reads.
 *
 * The catalog is the server's, so the tests serve it from MSW rather than handing the
 * component a literal. What is being checked is the consequence: that only offered
 * models are selectable, that an effort the newly chosen model cannot run is not
 * carried over, and that a model without reasoning hides the effort control entirely.
 */

const CATALOG = {
  defaultModel: "gpt-5-mini",
  defaultReasoningEffort: "low",
  models: [
    {
      id: "gpt-5-mini",
      name: "GPT-5 mini",
      provider: "openai",
      vision: true,
      reasoning: true,
      supportedEfforts: ["low", "medium"],
      contextWindow: 128000,
      maxOutputTokens: 8192,
      pricing: { inputUsdPerM: 0.25, outputUsdPerM: 2, cachedReadUsdPerM: 0.125 },
      isDefault: true,
    },
    {
      id: "gpt-5-nano",
      name: "GPT-5 nano",
      provider: "openai",
      vision: false,
      reasoning: false,
      supportedEfforts: ["none"],
      contextWindow: 64000,
      maxOutputTokens: 4096,
      pricing: { inputUsdPerM: 0.05, outputUsdPerM: 0.4, cachedReadUsdPerM: 0.025 },
      isDefault: false,
    },
  ],
}

/** Reads the selection the composer would actually forward to the next turn. */
function SelectionProbe() {
  const selectedModel = useAssistantStore((state) => state.selectedModel)
  const selectedEffort = useAssistantStore((state) => state.selectedEffort)
  return (
    <p data-testid="selection">
      {selectedModel ?? "none"}:{selectedEffort ?? "none"}
    </p>
  )
}

function renderSelector() {
  return render(
    <StoreProvider>
      <ModelSelector />
      <SelectionProbe />
    </StoreProvider>,
  )
}

function serveCatalog() {
  server.use(http.get("/v1/assistant/models", () => HttpResponse.json(CATALOG)))
}

describe("the model selector", () => {
  it("offers exactly the models the server allows", async () => {
    serveCatalog()
    renderSelector()

    const trigger = await screen.findByRole("button", { name: /Model:/ })
    await userEvent.click(trigger)

    // Both names also appear on the trigger, so the menu is what is counted.
    const options = await screen.findAllByRole("menuitem")
    expect(options.map((option) => option.textContent)).toEqual(["GPT-5 mini", "GPT-5 nano"])
  })

  it("starts on the server's default rather than a client-chosen one", async () => {
    serveCatalog()
    renderSelector()

    await waitFor(() => {
      expect(screen.getByTestId("selection").textContent).toBe("gpt-5-mini:low")
    })
  })

  it("carries a supported effort across a model change", async () => {
    serveCatalog()
    renderSelector()

    await userEvent.click(await screen.findByRole("button", { name: /Model:/ }))
    await userEvent.click(await screen.findByText("GPT-5 nano"))

    // nano supports only "none", so the previous "low" must not survive: the server
    // would refuse it, and the learner would see a control that lies.
    await waitFor(() => {
      expect(screen.getByTestId("selection").textContent).toBe("gpt-5-nano:none")
    })
  })

  it("hides the effort control for a model without reasoning", async () => {
    serveCatalog()
    renderSelector()

    await userEvent.click(await screen.findByRole("button", { name: /Model:/ }))
    await userEvent.click(await screen.findByText("GPT-5 nano"))

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Reasoning:/ })).toBeNull()
    })
  })

  it("renders nothing rather than an invented default when the catalog cannot be read", async () => {
    server.use(
      http.get("/v1/assistant/models", () =>
        HttpResponse.json({ code: "internal_error", detail: "boom" }, { status: 500 }),
      ),
    )
    renderSelector()

    await waitFor(() => {
      expect(screen.getByTestId("selection").textContent).toBe("none:none")
    })
    expect(screen.queryByRole("button", { name: /Model:/ })).toBeNull()
  })
})
