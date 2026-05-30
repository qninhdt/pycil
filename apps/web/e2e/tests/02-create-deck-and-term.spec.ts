/**
 * Spec 02: Create deck + view seeded terms.
 *
 * Creates a deck via the CreateNodeDialog, then navigates to the
 * deck terms page to verify the seeded term "ephemeral" appears.
 * The DB is pre-seeded by the db-seed fixture, so no LLM calls.
 */
import { test, expect } from "../fixtures/auth";
import { DashboardPage } from "../pages/dashboard-page";
import { DeckPage } from "../pages/deck-page";
import { seedDatabase, type SeededData } from "../fixtures/db-seed";

let seeded: SeededData;

test.beforeAll(() => {
  seeded = seedDatabase();
});

test.describe("02 view pre-seeded deck and terms", () => {
  test("dashboard shows start learning CTA when authenticated", async ({
    authenticatedPage,
  }) => {
    const page = await authenticatedPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.expectAuthenticated();
  });

  test("pre-seeded deck page loads", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const deck = new DeckPage(page, seeded.deckId);
    await deck.goto();
    await deck.expectLoaded();
  });

  test("deck terms page shows seeded term", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const deck = new DeckPage(page, seeded.deckId);
    await deck.goto();
    await deck.openTerms();
    await deck.expectTermVisible("ephemeral");
  });
});
