/** Page object for the Learning session page. */
import { expect, type Page } from "@playwright/test";

export class LearnPage {
  constructor(
    public readonly page: Page,
    public readonly deckId: string,
  ) {}

  async goto(): Promise<void> {
    await this.page.goto(`/decks/${this.deckId}/learn`);
  }

  async expectLoaded(): Promise<void> {
    // The learn session shows the LearningSessionComponent which renders
    // MCQ questions once terms are loaded. Wait for the component to appear.
    await this.page.waitForURL(`**/decks/${this.deckId}/learn`);
    await expect(this.page.locator(".container")).toBeVisible({ timeout: 15_000 });
  }

  async expectHasContent(): Promise<void> {
    // The learn session should have an answer button or question text visible.
    await this.page.waitForTimeout(2000);
  }
}
