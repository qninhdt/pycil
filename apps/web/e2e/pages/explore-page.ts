/** Page object for the Explore public decks page. */
import { expect, type Page } from "@playwright/test";

export class ExplorePage {
  constructor(public readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/explore");
  }

  async expectLoaded(): Promise<void> {
    await expect(
      this.page.getByRole("heading", { name: "Explore public decks" }),
    ).toBeVisible();
  }
}
