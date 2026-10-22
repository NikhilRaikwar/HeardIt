import type { NextConfig } from "next";

const configuredApiOrigin = process.env.API_INTERNAL_URL?.trim();

if (process.env.NODE_ENV === "production" && !configuredApiOrigin) {
  throw new Error("API_INTERNAL_URL must point to the HTTPS FastAPI deployment when building HeardIt for production.");
}

const apiOrigin = configuredApiOrigin || "http://127.0.0.1:8000";

if (process.env.NODE_ENV === "production" && !apiOrigin.startsWith("https://")) {
  throw new Error("API_INTERNAL_URL must use HTTPS in production.");
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` },
      { source: "/health/:path*", destination: `${apiOrigin}/health/:path*` },
    ];
  },
  async redirects() {
    return [
      { source: "/app/:path*", destination: "/create", permanent: false },
      { source: "/sign-in", destination: "/create", permanent: false },
      { source: "/demo", destination: "/", permanent: false },
      { source: "/docs", destination: "/", permanent: false },
    ];
  },
  async headers() {
    return [];
  },
};

export default nextConfig;
