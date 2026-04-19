/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow the orchestrator URL to be reached from the browser via NEXT_PUBLIC_*.
  // No rewrites: we hit the orchestrator directly so CORS already configured there applies.
};

export default nextConfig;
