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
//   - `cleartext: true` allows plain http:// (not https://) to that host.
//     This is fine specifically because Tailscale traffic is already fully
//     encrypted at the VPN layer between your devices — it never touches
//     the public internet in the clear. Don't point this at a public,
//     non-Tailscale http:// host.
const config: CapacitorConfig = {
  // Left as the original package id from before the JobPilot rename —
  // changing it would mean manually moving/renaming the native Java package
  // dir too (Capacitor has no "rename appId" command), and it's purely
  // internal plumbing, invisible to the user, so not worth the risk.
  appId: "ai.jobflow.app",
  appName: "JobPilot",
  webDir: "public",
  server: {
    url: "http://radalv11.tailb3d4c1.ts.net:3000",
    cleartext: true,
  },
};

export default config;
