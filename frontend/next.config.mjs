/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No `X-Powered-By: Next.js` — no reason to tell the internet the stack.
  poweredByHeader: false,
  // The app never uses next/image, and the image optimizer is where Next's
  // worst CVEs have lived (RCE via AVIF, DoS). Security headers are set in
  // middleware.ts.
  images: { unoptimized: true },
};

export default nextConfig;
