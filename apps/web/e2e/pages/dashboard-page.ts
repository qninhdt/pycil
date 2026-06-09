/** Page object for the Dashboard home page. */
import { expect, type Page } from "@playwright/test";

export class DashboardPage {
  constructor(public readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/");
  }

  async expectAuthenticated(): Promise<void> {
    await this.page.waitForURL((url) => !url.pathname.startsWith("/sign-in"));
    await expect(
      this.page.getByRole("heading", { name: "Start Learning Today" }),
    ).toBeVisible();
    await expect(
      this.page.getByRole("link", { name: "Browse Collection" }),
    ).toBeVisible();
  }

  async getUserAvatar(): Promise<ReturnType<Page["getByRole"]>> {
    return this.page.getByRole("button", { name: "User menu" });
  }

  async openCollection(): Promise<void> {
    await this.page.getByRole("link", { name: "Browse Collection" }).click();
  }
}
