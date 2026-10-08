import type { NextConfig } from "next";
import path from "node:path";

const configuredApiProxyTarget = process.env.API_PROXY_TARGET?.replace(/\/$/, "");
const apiProxyTarget = configuredApiProxyTarget || (
  process.env.VERCEL === "1" ? "https://ai-hackathon-judge-1.onrender.com" : ""
);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  output: "standalone",
  outputFileTracingRoot: path.resolve(process.cwd()),
  async rewrites() {
    if (!apiProxyTarget) return [];
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  },
};

export default nextConfig;
