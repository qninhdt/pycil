/** Page object for the Sign-in page. */
import { expect, type Page } from "@playwright/test";

export class SignInPage {
  constructor(public readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/sign-in");
  }

  async expectPageLoaded(): Promise<void> {
    await expect(
      this.page.getByRole("heading", { name: "Welcome to Pycil" }),
    ).toBeVisible();
    // Provider button label is env-driven (OIDC_PROVIDER_NAME). Match the stable
    // "Continue with" prefix so swapping Dex→Google does not break the assertion.
    await expect(
      this.page.getByRole("button", { name: /continue with/i }),
    ).toBeVisible();
  }

  /** Click the OIDC provider button → kicks off the real Auth.js → Dex flow. */
  async clickProviderLogin(): Promise<void> {
    await this.page.getByRole("button", { name: /continue with/i }).click();
  }
}
