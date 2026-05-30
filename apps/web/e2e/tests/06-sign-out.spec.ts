/**
 * Spec 06: Sign-out — clicking Log out clears session and redirects to sign-in.
 */
import { test, expect } from "../fixtures/auth";
import { DashboardPage } from "../pages/dashboard-page";
import { SignInPage } from "../pages/sign-in-page";

test.describe("06 sign-out", () => {
  test("sign-out redirects to sign-in page", async ({ authenticatedPage }) => {
    const page = await authenticatedPage();
    const dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.expectAuthenticated();

    // Open user menu via the avatar button.
    const avatar = page.getByRole("button", { name: "User menu" });
    await avatar.click();

    // Click Log out.
    const logOutItem = page.getByRole("menuitem", { name: /log out/i });
    await expect(logOutItem).toBeVisible();
    await logOutItem.click();

    // Should redirect to sign-in.
    const signIn = new SignInPage(page);
    await signIn.expectPageLoaded();
  });
});
