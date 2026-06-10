/**
 * Page object for the Dex login form (local OIDC IdP).
 *
 * Dex stands in for Google in local/staging/CI. The real browser OIDC dance
 * lands here after the app's "Continue with <provider>" button redirects to
 * Dex's /auth endpoint. Selectors target Dex's default password-connector
 * template (image pinned to ghcr.io/dexidp/dex:v2.41.1 in docker-compose.staging.yml):
 *   - email/username  → input[name="login"]  (id="login")
 *   - password        → input[name="password"] (id="password")
 *   - submit          → button[type="submit"]
 * skipApprovalScreen=true (infra/dex/config.yaml) means no consent click — Dex
 * redirects straight back to the app callback after a successful password post.
 */
import { expect, type Page } from "@playwright/test";

export class DexLoginPage {
  constructor(public readonly page: Page) {}

  /** True once the Dex login form is the active document (issuer host + form). */
  async expectLoaded(): Promise<void> {
    await expect(this.page.locator('input[name="login"]')).toBeVisible({
      timeout: 20_000,
    });
    await expect(this.page.locator('input[name="password"]')).toBeVisible();
  }

  /**
   * Fill the Dex password form and submit. Does NOT wait for the callback —
   * the caller owns the post-login navigation wait (it knows the expected
   * authenticated landing URL).
   */
  async login(email: string, password: string): Promise<void> {
    await this.page.locator('input[name="login"]').fill(email);
    await this.page.locator('input[name="password"]').fill(password);
    await this.page.locator('button[type="submit"]').click();
  }
}
