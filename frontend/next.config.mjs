/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // The browser talks to the backend through a relative /api/* path so the
  // same code works in dev (Next dev server proxies via rewrites) and in
  // prod (reverse proxy in front of both services).
  async rewrites() {
    const backend = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/:path*` },
    ];
  },
};

export default nextConfig;
