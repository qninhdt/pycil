/**
 * Playwright `setup` project: log in once via real Dex, save the session.
 *
 * Runs before the chromium test project (see playwright.config.ts `dependencies`).
 * Every spec that uses `authenticatedPage()` with no explicit user loads this
 * stored session, so only ONE real OIDC round-trip happens per run — faster and
 * gentler on Dex than logging in per-test.
 *
 * Hard precondition lives in the live-profile guard (checked separately); this
 * file only owns the login + storageState capture.
 */
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { test as setup, expect } from "@playwright/test";
import { loginViaDex, STORAGE_STATE, DEFAULT_USER } from "./fixtures/auth";

setup("authenticate via Dex", async ({ page }) => {
  await loginViaDex(page, DEFAULT_USER);

  // Prove the session actually took before saving: a protected route must NOT
  // bounce back to /sign-in. A blank/invalid storageState would silently fail
  // every downstream spec with a confusing redirect instead of a clear error.
  await page.goto("/");
  await expect(page).toHaveURL((url) => !url.pathname.startsWith("/sign-in"), {
    timeout: 20_000,
  });

  mkdirSync(dirname(STORAGE_STATE), { recursive: true });
  await page.context().storageState({ path: STORAGE_STATE });
});
