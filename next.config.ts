import type { NextConfig } from "next";

// Keep browser bearer tokens same-origin in local development. Deployments can
// point this server-side value at their API service without exposing it to the browser.
const apiOrigin = (process.env.API_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` }];
  },
};
export default nextConfig;
