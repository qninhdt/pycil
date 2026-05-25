/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    serverActions: { allowedOrigins: [process.env.DOMAIN || "localhost"] },
  },
};

export default nextConfig;
