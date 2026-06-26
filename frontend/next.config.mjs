/** @type {import('next').NextConfig} */
const nextConfig = {
  // Strict mode double-invokes effects in dev which doubles all API calls.
  // Re-enable for production builds; keep off during active development.
  reactStrictMode: false,
  async rewrites() {
    // Proxy API calls to the FastAPI backend during development so the browser
    // talks to a single origin (no CORS hassle for same-origin fetches).
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
