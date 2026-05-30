/**
 * JWT-based auth fixture for Playwright e2e tests.
 *
 * Bypasses Google OAuth by minting a JWT with `jose` and
 * injecting it as the session cookie (`pycil-session` in dev).
 * Supports both dev (non-secure) and CI (secure if HTTPS).
 */
import { test as base, type Page } from "@playwright/test";
import { SignJWT } from "jose";

export interface AuthFixture {
  /** Page authenticated as the given user. */
  authenticatedPage: (user?: TestUser) => Promise<Page>;
}

export interface TestUser {
  id: string;
  email: string;
  name: string;
  image?: string;
  role?: string;
  tokenVersion?: number;
}

const DEFAULT_USER: TestUser = {
  id: "00000000-0000-0000-0000-00000000e2e1",
  email: "e2e-test@pycil.local",
  name: "E2E Test User",
  role: "user",
  tokenVersion: 0,
};

function cookieName(): string {
  return process.env.SESSION_COOKIE_NAME ?? "pycil-session";
}

async function mintJwt(
  secret: string,
  user: TestUser,
  maxAgeSeconds: number = 604800,
): Promise<string> {
  const key = new TextEncoder().encode(secret);
  return new SignJWT({
    sub: user.id,
    email: user.email,
    name: user.name,
    picture: user.image ?? null,
    role: user.role ?? "user",
    tv: user.tokenVersion ?? 0,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(`${maxAgeSeconds}s`)
    .sign(key);
}

export const test = base.extend<AuthFixture>({
  authenticatedPage: [
    async ({ browser }, use) => {
      const secret =
        process.env.AUTH_JWT_SECRET ?? "e2e-fake-jwt-secret-for-testing";
      const maxAge = Number(
        process.env.JWT_MAX_AGE_SECONDS ?? 60 * 60 * 24 * 7,
      );

      async function createAuthPage(user: TestUser = DEFAULT_USER): Promise<Page> {
        const context = await browser.newContext();
        const jwt = await mintJwt(secret, user, maxAge);
        await context.addCookies([
          {
            name: cookieName(),
            value: jwt,
            domain: "localhost",
            path: "/",
            httpOnly: true,
            sameSite: "Lax",
          },
        ]);
        return context.newPage();
      }

      await use(createAuthPage);
    },
    { scope: "test" },
  ],
});

export { expect } from "@playwright/test";
