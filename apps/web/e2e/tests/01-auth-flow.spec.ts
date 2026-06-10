/**
 * Spec 01: Auth flow — real OIDC redirect (no minted cookie).
 *
 * Unauthenticated users hitting a protected route are bounced to /sign-in, and
 * clicking the provider button drives the real Auth.js → Dex redirect (the
 * browser lands on the Dex-issued login form). Authenticated users (session
 * captured once by the setup project) reach the dashboard.
 */
import { test, expect } from "../fixtures/auth";
import { SignInPage } from "../pages/sign-in-page";
import { DashboardPage } from "../pages/dashboard-page";

test.describe("01 authentication flow", () => {
  test("unauthenticated user sees sign-in page", async ({ page }) => {
    const signIn = new SignInPage(page);
    await signIn.goto();
    await signIn.expectPageLoaded();
  });

  test("unauthenticated request to protected page redirects to sign-in", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL(/\/sign-in/);
    await expect(
      page.getByRole("heading", { name: "Welcome to Pycil" }),
    ).toBeVisible();
  });

  test("clicking the provider button redirects to the real Dex login", async ({
    page,
  }) => {
    const signIn = new SignInPage(page);
    await signIn.goto();
    await signIn.expectPageLoaded();
    // Real OIDC dance: the provider button kicks Auth.js → Dex /auth, and the
    // browser lands on the Dex-hosted password form (issuer host + login field).
    await page.getByRole("button", { name: /continue with/i }).click();
    await expect(page.locator('input[name="login"]')).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.locator('input[name="password"]')).toBeVisible();
  });

  test("authenticated user lands on dashboard", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.expectAuthenticated();
  });
});
