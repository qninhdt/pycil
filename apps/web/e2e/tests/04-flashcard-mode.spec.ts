/**
 * Spec 04: Flashcard mode — flashcard mode loads with pre-seeded enriched terms.
 */
import { test } from "../fixtures/auth";
import { DeckPage } from "../pages/deck-page";
import { FlashcardPage } from "../pages/flashcard-page";
import { seedDatabase, type SeededData } from "../fixtures/db-seed";

let seeded: SeededData;

test.beforeAll(() => {
  seeded = seedDatabase();
});

test.describe("04 flashcard mode", () => {
  test("flashcard mode loads on pre-seeded deck", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const deck = new DeckPage(page, seeded.deckId);
    await deck.goto();
    await deck.expectLoaded();
    await deck.clickFlashcard();
    const flashcard = new FlashcardPage(page, seeded.deckId);
    await flashcard.expectLoaded();
  });
});
