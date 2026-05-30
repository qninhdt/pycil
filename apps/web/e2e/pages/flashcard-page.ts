/** Page object for the Flashcard mode page. */
import { expect, type Page } from "@playwright/test";

export class FlashcardPage {
  constructor(
    public readonly page: Page,
    public readonly deckId: string,
  ) {}

  async goto(): Promise<void> {
    await this.page.goto(`/decks/${this.deckId}/flashcard`);
  }

  async expectLoaded(): Promise<void> {
    await this.page.waitForURL(`**/decks/${this.deckId}/flashcard`);
    // FlashcardDeck component should be visible with at least one card.
    await expect(this.page.locator(".aspect-\\[4\\/3\\], .aspect-\\[16\\/9\\], .h-full").first()).toBeVisible({ timeout: 15_000 });
  }
}
