import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // the Docker image runs the self-contained server in .next/standalone
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
