/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    const dest = process.env.API_INTERNAL_URL || "http://localhost:8000";
    return [
      { source: "/backend/:path*", destination: `${dest}/:path*` },
    ];
  },
};

module.exports = nextConfig;
