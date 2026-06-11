/**
 * Spec 07 (LIVE): real term enrichment through the worker.
 *
 * Adds a term through the real Add-Term dialog → core enqueues generate_term →
 * the worker enriches it (stub profile: canned TermGenerationOutput; live
 * profile: real OpenRouter) → definition + example rows land. Asserts on
 * STRUCTURE (≥1 definition, ≥1 example, a CEFR level present), never on exact
 * LLM text, so it is stable under both profiles.
 *
 * Worker-gated: runs only where a worker consumes the job (local staging +
 * nightly), NOT the per-PR CI e2e job. Set E2E_WORKER_SPECS=true to enable it.
 * The stub profile still exercises the full enqueue→worker→DB path — a
 * test-speed tier, not a mock of the product surface.
 *
 * Polls the DB (readDefinitions) with a generous deadline rather than sleeping:
 * generation is an async arq job whose latency varies (worker cold-start, model
 * latency under the live profile).
 */
import { test, expect } from "../fixtures/auth";
import { DeckPage } from "../pages/deck-page";
import {
  seedEmptyDeck,
  readTermIdByValue,
  readDefinitions,
  type EmptyDeckSeed,
} from "../fixtures/db-seed";

// A term unlikely to collide with other specs' seeds. Lowercase: the add-term
// path normalizes, and the deck term list renders the normalized value.
const LIVE_TERM = "serendipitous";
const ENRICH_DEADLINE_MS = 120_000;
const POLL_INTERVAL_MS = 2_000;
const RUN_WORKER_SPECS = process.env["E2E_WORKER_SPECS"] === "true";

let seeded: EmptyDeckSeed;

test.beforeAll(() => {
  if (!RUN_WORKER_SPECS) return;
  seeded = seedEmptyDeck();
});

test.describe("07 live term enrichment", () => {
  test.skip(!RUN_WORKER_SPECS, "requires pycil worker; excluded from per-PR CI");

  // The whole flow (UI add + async worker enrichment) can take a while under
  // the live profile; give the test itself room beyond the default 60s.
  test.setTimeout(ENRICH_DEADLINE_MS + 60_000);

  test("adding a term enriches it with real LLM-generated definitions", async ({
    authenticatedPage,
  }) => {
    const page = await authenticatedPage();
    const deck = new DeckPage(page, seeded.deckId);
    await deck.goto();
    // Empty deck still renders its header; wait for the deck shell, not the
    // "E2E Starter Deck" heading (this is a differently-named live deck).
    await page.waitForURL(`**/decks/${seeded.deckId}`);

    // The Add-Term control lives on the Terms tab (the Overview tab only shows
    // an empty-state card). Switch to it first — matches the passing spec 02.
    await deck.openTerms();

    // Open the Add-Term dialog, type the term, submit. The dialog mounts a
    // JobStreamWatcher that holds the dialog open until the job completes.
    await page.getByRole("button", { name: /add term/i }).first().click();
    // Scope to the open dialog: "Term" label + "Add term" submit both have
    // page-level namesakes (search box, toolbar/trigger buttons) that trip
    // Playwright strict mode otherwise.
    const dialog = page.getByRole("dialog");
    const input = dialog.getByLabel("Term");
    await expect(input).toBeVisible({ timeout: 15_000 });
    await input.fill(LIVE_TERM);
    await dialog.getByRole("button", { name: /^add term$/i }).click();

    // The term row must resolve in the DB (core inserted terms + deck_terms
    // synchronously on the POST; enrichment is the async part).
    await expect
      .poll(() => readTermIdByValue(LIVE_TERM), {
        message: "term row should exist after add",
        timeout: 30_000,
        intervals: [1_000],
      })
      .not.toBeNull();
    const termId = readTermIdByValue(LIVE_TERM);
    expect(termId).not.toBeNull();

    // Poll the DB until the worker lands the enriched definition + example.
    // Structural assertion only — never the exact generated text.
    await expect
      .poll(() => readDefinitions(termId as number).count, {
        message: "worker should enrich at least one definition",
        timeout: ENRICH_DEADLINE_MS,
        intervals: [POLL_INTERVAL_MS],
      })
      .toBeGreaterThan(0);
    const defs = readDefinitions(termId as number);

    expect(defs.count, "≥1 definition enriched").toBeGreaterThan(0);
    expect(defs.exampleCount, "≥1 example sentence").toBeGreaterThan(0);
    expect(defs.cefrLevels.length, "CEFR level present").toBeGreaterThan(0);
  });
});
