import NextAuth from "next-auth";
import { SignJWT, jwtVerify, type JWTPayload } from "jose";

import { authConfig } from "./auth.config";

const secret = new TextEncoder().encode(process.env.AUTH_JWT_SECRET);
const internalSecret = process.env.INTERNAL_API_SECRET ?? "";
const internalUrl =
  process.env.PYCIL_CORE_INTERNAL_URL ?? "http://pycil-core:8000";
const maxAge = Number(process.env.JWT_MAX_AGE_SECONDS ?? 60 * 60 * 24 * 7);
const oidcProviderId = process.env.OIDC_PROVIDER_ID ?? "oidc";

interface UpsertUserResult {
  user_id: string;
  role: string;
  token_version: number;
}

async function upsertUser(payload: {
  email: string;
  name?: string | null;
  image?: string | null;
}): Promise<UpsertUserResult> {
  const delays = [250, 1000, 4000];
  let lastErr: unknown = null;
  for (let attempt = 0; attempt < delays.length; attempt++) {
    try {
      const res = await fetch(`${internalUrl}/auth/upsert-user`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-internal-secret": internalSecret,
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const data = (await res.json()) as UpsertUserResult;
        return data;
      }
      if (res.status < 500) {
        throw new Error(`upsert-user failed ${res.status}`);
      }
      lastErr = new Error(`upsert-user 5xx ${res.status}`);
    } catch (err) {
      lastErr = err;
    }
    await new Promise((r) => setTimeout(r, delays[attempt]));
  }
  throw lastErr ?? new Error("upsert-user failed");
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  secret: process.env.AUTH_JWT_SECRET,
  session: { strategy: "jwt", maxAge },
  providers: [
    {
      id: oidcProviderId,
      name: process.env.OIDC_PROVIDER_NAME ?? "SSO",
      type: "oidc",
      issuer: process.env.OIDC_ISSUER_URL,
      clientId: process.env.OIDC_CLIENT_ID,
      clientSecret: process.env.OIDC_CLIENT_SECRET,
      checks: ["pkce", "state"],
    },
  ],
  callbacks: {
    ...authConfig.callbacks,
    async signIn({ user, profile }) {
      const email = user.email ?? profile?.email;
      if (!email) return false;
      // Identity is email-keyed in core, so an IdP that lets a user self-assert
      // an unverified email is an account-takeover vector. Reject explicit
      // non-verification. (Absent claim passes: Google always sets it true;
      // Dex static users omit it rather than setting false.)
      if (profile?.email_verified === false) return false;
      try {
        const result = await upsertUser({
          email,
          name: user.name ?? profile?.name ?? null,
          image: user.image ?? (profile?.picture as string | undefined) ?? null,
        });
        const u = user as {
          id?: string;
          role?: string;
          tokenVersion?: number;
        };
        u.id = result.user_id;
        u.role = result.role;
        u.tokenVersion = result.token_version;
        return true;
      } catch {
        return false;
      }
    },
    async jwt({ token, user }) {
      if (user && (user as { id?: string }).id) {
        const u = user as {
          id?: string;
          role?: string;
          tokenVersion?: number;
        };
        token.sub = u.id;
        token.tv = u.tokenVersion ?? 0;
        token.role = u.role ?? "user";
        token.email = user.email ?? token.email;
        token.name = user.name ?? token.name;
        token.picture = user.image ?? token.picture;
      }
      return token;
    },
    async session({ session, token }) {
      if (token.sub) (session.user as { id?: string }).id = token.sub;
      if (typeof token.role === "string") {
        (session.user as { role?: string }).role = token.role;
      }
      return session;
    },
  },
  jwt: {
    async encode({ token }) {
      const payload: JWTPayload = { ...(token ?? {}) };
      if (payload.tv === undefined) payload.tv = 0;
      if (payload.role === undefined) payload.role = "user";
      return await new SignJWT(payload)
        .setProtectedHeader({ alg: "HS256" })
        .setIssuedAt()
        .setExpirationTime(`${maxAge}s`)
        .sign(secret);
    },
    async decode({ token }) {
      if (!token) return null;
      const { payload } = await jwtVerify(token, secret, {
        algorithms: ["HS256"],
      });
      return payload as JWTPayload;
    },
  },
});
