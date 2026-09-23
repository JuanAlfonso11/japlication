import { NextResponse, type NextRequest } from "next/server";

// Security headers for every page. JobPilot is reachable from the public
// internet (tailscale funnel) and keeps its session tokens in localStorage,
// so an XSS would walk off with the session — the CSP is what stops an
// injected script from running or from phoning home.
//
// The script policy is nonce-based: Next reads the nonce back out of the
// request's Content-Security-Policy header and stamps it on its own inline
// scripts; layout.tsx does the same for the theme script.

const API_ORIGIN = new URL(
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
).origin;

// ponytail: Capacitor's WebView (Android UA carries "; wv)") injects its
// native bridge as an inline <script> with no nonce, so a nonce policy would
// kill every plugin (push, share, filesystem, back button). There, scripts
// fall back to 'unsafe-inline'; every other directive still applies. Upgrade
// path: have the APK send the nonce-less bridge via addDocumentStartJavaScript.
function isAndroidWebView(ua: string): boolean {
  return /; wv\)/.test(ua);
}

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const dev = process.env.NODE_ENV === "development";
  const scriptSrc = isAndroidWebView(request.headers.get("user-agent") ?? "")
    ? "'self' 'unsafe-inline'"
    : `'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`;

  const csp = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    // framer-motion and Tailwind transitions write style attributes.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self' ${API_ORIGIN}${dev ? " ws:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  response.headers.set("Strict-Transport-Security", "max-age=31536000");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: static chunks carry no HTML to protect, and skipping them
      // keeps the middleware off the hot path.
      source: "/((?!_next/static|_next/image|favicon.ico|icons/|offline.html).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
