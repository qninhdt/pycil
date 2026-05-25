/**
 * Shared Postgres pool for server components / route handlers.
 *
 * Auth.js adapter, SSE handler, and any future server-side reads share this
 * pool. Module-singleton pattern survives Next.js dev hot-reloads via globalThis.
 */
import { Pool } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var __pycilPgPool: Pool | undefined;
}

export const pool: Pool =
  globalThis.__pycilPgPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 5,
  });

if (process.env.NODE_ENV !== "production") {
  globalThis.__pycilPgPool = pool;
}
