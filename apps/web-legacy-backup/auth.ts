import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";

import { authConfig } from "./auth.config";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 5,
});

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PostgresAdapter(pool),
  session: { strategy: "database" },
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],
});
