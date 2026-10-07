import type { NextConfig } from "next";
import path from "node:path";
const nextConfig: NextConfig = { poweredByHeader: false, outputFileTracingRoot: path.resolve(process.cwd()) };
export default nextConfig;
