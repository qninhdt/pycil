/** Page object for deck detail + terms pages. */
import { expect, type Page } from "@playwright/test";

export class DeckPage {
  constructor(
    public readonly page: Page,
    public readonly deckId: string,
  ) {}

  async goto(): Promise<void> {
    await this.page.goto(`/decks/${this.deckId}`);
  }

  async expectLoaded(): Promise<void> {
    await expect(
      this.page.getByRole("heading", { name: "E2E Starter Deck" }),
    ).toBeVisible({ timeout: 10_000 });
  }

  async openTerms(): Promise<void> {
    await this.page.getByRole("tab", { name: /terms/i }).click();
  }

  async expectTermVisible(value: string): Promise<void> {
    await expect(this.page.getByText(value, { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  }

  async clickLearn(): Promise<void> {
    await this.page.getByRole("link", { name: "Learn" }).click();
  }

  async clickFlashcard(): Promise<void> {
    await this.page.getByRole("link", { name: "Flashcard" }).click();
  }

  get learnButton(): ReturnType<Page["getByRole"]> {
    return this.page.getByRole("link", { name: "Learn" });
  }

  get flashcardButton(): ReturnType<Page["getByRole"]> {
    return this.page.getByRole("link", { name: "Flashcard" });
  }
}
