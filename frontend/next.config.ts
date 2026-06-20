import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server build for Azure App Service (small artifact, no OOM
  // on the B1 plan; deploy `.next/standalone` and run `node server.js`).
  output: "standalone",
};

export default nextConfig;
