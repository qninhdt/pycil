import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { SignJWT, jwtVerify, type JWTPayload } from "jose";

import { authConfig } from "./auth.config";

const secret = new TextEncoder().encode(process.env.AUTH_JWT_SECRET);
const internalSecret = process.env.INTERNAL_API_SECRET ?? "";
const internalUrl =
  process.env.PYCIL_CORE_INTERNAL_URL ?? "http://pycil-core:8000";
const maxAge = Number(process.env.JWT_MAX_AGE_SECONDS ?? 60 * 60 * 24 * 7);

async function upsertUser(payload: {
  google_sub: string;
  email: string;
  name?: string | null;
  image?: string | null;
}): Promise<string> {
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
        const data = (await res.json()) as { user_id: string };
        return data.user_id;
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
  session: { strategy: "jwt", maxAge },
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      checks: ["pkce", "state"],
    }),
  ],
  callbacks: {
    ...authConfig.callbacks,
    async signIn({ user, account }) {
      if (!account || account.provider !== "google") return false;
      if (!user.email) return false;
      try {
        const userId = await upsertUser({
          google_sub: account.providerAccountId,
          email: user.email,
          name: user.name ?? null,
          image: user.image ?? null,
        });
        (user as { id?: string }).id = userId;
        return true;
      } catch {
        return false;
      }
    },
    async jwt({ token, user }) {
      if (user && (user as { id?: string }).id) {
        token.sub = (user as { id?: string }).id;
        token.tv = 0;
        token.email = user.email ?? token.email;
        token.name = user.name ?? token.name;
        token.picture = user.image ?? token.picture;
      }
      return token;
    },
    async session({ session, token }) {
      if (token.sub) (session.user as { id?: string }).id = token.sub;
      return session;
    },
  },
  jwt: {
    async encode({ token }) {
      const payload: JWTPayload = { ...(token ?? {}) };
      if (payload.tv === undefined) payload.tv = 0;
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
