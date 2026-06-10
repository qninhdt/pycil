import type { NextConfig } from "next";

const devProxyTarget =
  process.env.NEXT_DEV_PROXY_TARGET ?? "http://localhost:8000";

// Safety guard: the frontend mock mode bypasses auth and runs on in-browser
// fixtures. NEXT_PUBLIC_USE_MOCK is inlined at build time, so a production build
// that accidentally has it set would ship a permanent, silent auth bypass.
// Fail the build loudly instead. Set ALLOW_MOCK_PROD=true to opt out (e.g. a
// hosted demo that is intentionally backend-free).
if (
  process.env.NEXT_PUBLIC_USE_MOCK === "true" &&
  process.env.NODE_ENV === "production" &&
  process.env.ALLOW_MOCK_PROD !== "true"
) {
  throw new Error(
    "NEXT_PUBLIC_USE_MOCK=true in a production build. This bypasses auth and " +
      "uses mock data. Unset it, or set ALLOW_MOCK_PROD=true for an intentional " +
      "backend-free demo build.",
  );
}

// PWA: this app ships a hand-written service worker at `public/sw.js`
// (registered via `src/lib/pwa-register.ts`). The `next-pwa` plugin was
// scaffolded but never installed (absent from the lockfile) and is
// incompatible with Next 15 + Turbopack; it also generates a competing
// `sw.js` that would clobber the custom one. Dropped to keep `next build`
// working and avoid a second service-worker mechanism.
const nextConfig: NextConfig = {
  async rewrites() {
    // The same-origin /api/core proxy exists for local dev (real prod calls core
    // directly via NEXT_PUBLIC_API_BASE, cross-origin on Vercel). E2E_PROXY lets
    // a production build (next build && next start) keep that same-origin proxy
    // so browser requests carry a consistent Origin for the core CSRF allowlist.
    // Real prod never sets E2E_PROXY, so its direct-call behavior is unchanged.
    if (process.env.NODE_ENV !== "development" && process.env.E2E_PROXY !== "true")
      return [];
    return [
      {
        source: "/api/core/:path*",
        destination: `${devProxyTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
