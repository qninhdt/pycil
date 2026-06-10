/**
 * Real-login auth fixture for Playwright e2e tests.
 *
 * Replaces the old hand-minted JWT cookie with a real browser login against the
 * Dex OIDC IdP — the same flow a human (and prod, swapping Dex→Google) uses.
 * The session cookie is issued by the genuine Auth.js round-trip, so the tests
 * exercise the actual auth path instead of a bypass.
 *
 * `authenticatedPage()` reuses the storageState captured once by the `setup`
 * project (see playwright.config.ts) so only one real login happens per run.
 * Pass an explicit user to force a fresh login as a different identity.
 */
import { test as base, type Page, type BrowserContext } from "@playwright/test";
import { DexLoginPage } from "../pages/dex-login-page";

export interface AuthFixture {
  /** Page authenticated as the given user (default: reuse stored session). */
  authenticatedPage: (user?: TestUser) => Promise<Page>;
}

export interface TestUser {
  email: string;
  password: string;
}

export const DEFAULT_USER: TestUser = {
  email: process.env.E2E_TEST_EMAIL ?? "e2e-test@pycil.local",
  password: process.env.E2E_TEST_PASSWORD ?? "password123",
};

/** Absolute path of the stored session, shared with the setup project. */
export const STORAGE_STATE =
  process.env.E2E_STORAGE_STATE ?? "e2e/.auth/user.json";

/**
 * Drive the real OIDC login: sign-in page → provider button → Dex form →
 * redirect back to an authenticated app route. Throws if the post-login URL is
 * still /sign-in (login did not take).
 */
export async function loginViaDex(
  page: Page,
  user: TestUser = DEFAULT_USER,
): Promise<void> {
  await page.goto("/sign-in");
  // The provider button label is env-driven (OIDC_PROVIDER_NAME, "Dex" locally).
  // Match the stable "Continue with" prefix so a provider rename does not break.
  await page.getByRole("button", { name: /continue with/i }).click();

  const dex = new DexLoginPage(page);
  await dex.login(user.email, user.password);

  // Auth.js consumes the callback, sets the session cookie, and redirects to the
  // app. Dex skipApprovalScreen=true means no consent click. Land off /sign-in.
  await page.waitForURL((url) => !url.pathname.startsWith("/sign-in"), {
    timeout: 30_000,
  });
}

export const test = base.extend<AuthFixture>({
  authenticatedPage: [
    async ({ browser }, use) => {
      const contexts: BrowserContext[] = [];

      async function createAuthPage(user?: TestUser): Promise<Page> {
        // No explicit user → reuse the session captured by the setup project.
        // Explicit user → fresh context + real login as that identity.
        let context: BrowserContext;
        if (!user) {
          context = await browser.newContext({ storageState: STORAGE_STATE });
          contexts.push(context);
          return context.newPage();
        }
        context = await browser.newContext();
        contexts.push(context);
        const page = await context.newPage();
        await loginViaDex(page, user);
        return page;
      }

      await use(createAuthPage);

      for (const c of contexts) await c.close();
    },
    { scope: "test" },
  ],
});

export { expect } from "@playwright/test";
