/**
 * Spec 03: Learning session — Learn mode loads with pre-seeded enriched terms.
 *
 * The pre-seeded deck has one term with a full definition (paraphrases,
 * examples, synonyms). The LearningSessionComponent fetches terms and
 * renders an MCQ-based session. No LLM calls needed.
 */
import { test } from "../fixtures/auth";
import { DeckPage } from "../pages/deck-page";
import { LearnPage } from "../pages/learn-page";
import { seedDatabase, type SeededData } from "../fixtures/db-seed";

let seeded: SeededData;

test.beforeAll(() => {
  seeded = seedDatabase();
});

test.describe("03 learning session", () => {
  test("learn mode loads on pre-seeded deck", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const deck = new DeckPage(page, seeded.deckId);
    await deck.goto();
    await deck.expectLoaded();
    await deck.clickLearn();
    const learn = new LearnPage(page, seeded.deckId);
    await learn.expectLoaded();
  });
});
