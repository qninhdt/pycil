import type { NextConfig } from "next";
import withPWAInit from "next-pwa";

const devProxyTarget =
  process.env.NEXT_DEV_PROXY_TARGET ?? "http://localhost:8000";

const withPWA = withPWAInit({
  dest: "public",
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === "development",
  runtimeCaching: [
    {
      urlPattern: /\/api\/core\/.*/,
      handler: "NetworkOnly",
    },
    {
      urlPattern: /\.(?:js|css|woff2?|png|svg|webp|ico)$/,
      handler: "CacheFirst",
      options: {
        cacheName: "pycil-static",
        expiration: { maxAgeSeconds: 30 * 86400 },
      },
    },
    {
      urlPattern: /\/_next\/image\?.*/,
      handler: "StaleWhileRevalidate",
    },
  ],
});

const nextConfig: NextConfig = {
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [
      {
        source: "/api/core/:path*",
        destination: `${devProxyTarget}/:path*`,
      },
    ];
  },
};

export default withPWA(nextConfig as never);
