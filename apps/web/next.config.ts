import type { NextConfig } from "next";

const devProxyTarget =
  process.env.NEXT_DEV_PROXY_TARGET ?? "http://localhost:8000";

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

export default nextConfig;
