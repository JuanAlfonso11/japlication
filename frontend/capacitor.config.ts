import type { CapacitorConfig } from "@capacitor/cli";

// JobPilot's Android app is a thin native shell — it never bundles the
// web app, it just points the WebView at the live Next.js server (same
// approach as opening the site in a mobile browser, but as an installable
// app with its own icon and no browser chrome). That means:
//   - There's nothing to rebuild the APK for when frontend code changes —
//     only `server.url` itself, native plugins, or the icon ever need a
//     rebuild.
//   - `server.url` MUST be reachable from the phone wherever it's used, not
//     just on the home Wi-Fi. See docs/ANDROID_APP.md — reached over
//     Tailscale (a private VPN mesh between only your own devices, no
//     router configuration needed), never a public port-forward. The
//     hostname below is this PC's Tailscale MagicDNS name — stable as long
//     as the machine keeps the same Tailscale identity (unlike a DHCP LAN
//     IP, it doesn't change on router reboots).
//   - Served over real HTTPS via `tailscale serve` — tailscaled itself
//     terminates TLS with an auto-renewing Tailscale-issued cert and proxies
//     to the plain-http Docker containers (localhost:3000/:8000) on this PC.
//     No cleartext exception needed anywhere anymore.
const config: CapacitorConfig = {
  // Left as the original package id from before the JobPilot rename —
  // changing it would mean manually moving/renaming the native Java package
  // dir too (Capacitor has no "rename appId" command), and it's purely
  // internal plumbing, invisible to the user, so not worth the risk.
  appId: "ai.jobflow.app",
  appName: "JobPilot",
  webDir: "public",
  server: {
    url: "https://jobpilot.tailb3d4c1.ts.net",
    // Without this, Capacitor's WebView blocks navigation to any origin
    // outside server.url — needed here because tapping the verification
    // email's link (see AndroidManifest.xml's intent-filter + MainActivity)
    // sends the WebView to the *backend* on :8443, a different origin than
    // the frontend on :443 even though it's the same Tailscale host.
    allowNavigation: ["jobpilot.tailb3d4c1.ts.net"],
    // Capacitor's own WebViewClient (BridgeWebViewClient) already loads
    // this bundled local page automatically whenever the main-frame
    // request to server.url fails for ANY reason — DNS never resolving
    // because the phone's own Tailscale VPN isn't connected
    // (net::ERR_NAME_NOT_RESOLVED, since the hostname only resolves
    // through Tailscale's MagicDNS), connection refused because the PC is
    // off, or a plain timeout. public/offline.html is bundled straight
    // into the APK (not fetched over the network), so it renders with
    // zero connectivity of any kind — no custom native WebViewClient code
    // needed, this is a stock Capacitor config option.
    errorPath: "offline.html",
  },
};

export default config;
