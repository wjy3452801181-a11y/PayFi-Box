import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: path.join(process.cwd(), "../../"),
  transpilePackages: ["@payfi-box/shared"],
  async headers() {
    const noStoreHeaders = [
      {
        key: "Cache-Control",
        value: "no-store, no-cache, must-revalidate, proxy-revalidate",
      },
      {
        key: "Pragma",
        value: "no-cache",
      },
      {
        key: "Expires",
        value: "0",
      },
    ];

    return [
      {
        source: "/",
        headers: noStoreHeaders,
      },
      {
        source: "/command-center",
        headers: noStoreHeaders,
      },
      {
        source: "/balance",
        headers: noStoreHeaders,
      },
      {
        source: "/merchant",
        headers: noStoreHeaders,
      },
      {
        source: "/mcp",
        headers: noStoreHeaders,
      },
      {
        source: "/modes",
        headers: noStoreHeaders,
      },
      {
        source: "/payments/:path*",
        headers: noStoreHeaders,
      },
    ];
  },
};

export default nextConfig;
