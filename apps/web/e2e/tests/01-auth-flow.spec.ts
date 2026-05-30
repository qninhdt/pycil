/**
 * Spec 01: Auth flow — sign-in page loads for unauthenticated users,
 * and authenticated users are redirected to dashboard.
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

  test("authenticated user lands on dashboard", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.expectAuthenticated();
  });
});
