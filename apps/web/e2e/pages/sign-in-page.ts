/** Page object for the Sign-in page. */
import { expect, type Page } from "@playwright/test";

export class SignInPage {
  constructor(public readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/sign-in");
  }

  async expectPageLoaded(): Promise<void> {
    await expect(this.page.getByRole("heading", { name: "Welcome to Pycil" })).toBeVisible();
    await expect(
      this.page.getByRole("button", { name: "Continue with Google" }),
    ).toBeVisible();
  }
}
