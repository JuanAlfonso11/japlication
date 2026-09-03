import type { CapacitorConfig } from "@capacitor/cli";

// JobFlow AI's Android app is a thin native shell — it never bundles the
// web app, it just points the WebView at the live Next.js server (same
// approach as opening the site in a mobile browser, but as an installable
// app with its own icon and no browser chrome). That means:
//   - There's nothing to rebuild the APK for when frontend code changes —
//     only `server.url` itself, native plugins, or the icon ever need a
//     rebuild.
//   - `server.url` MUST be reachable from the phone wherever it's used, not
//     just on the home Wi-Fi. See docs/ANDROID_APP.md — the recommended
//     setup is a Tailscale hostname/IP, never a public port-forward.
//   - `cleartext: true` allows plain http:// (not https://) to that host.
//     This is fine specifically because Tailscale traffic is already fully
//     encrypted at the VPN layer between your devices — it never touches
//     the public internet in the clear. Don't point this at a public,
//     non-Tailscale http:// host.
const config: CapacitorConfig = {
  appId: "ai.jobflow.app",
  appName: "JobFlow AI",
  webDir: "public",
  server: {
    // Placeholder — replace with your Tailscale MagicDNS hostname (or
    // Tailscale IP) once it's set up, e.g. "http://my-pc.tailnet-name.ts.net:3000".
    // Then re-run `npx cap sync android` and rebuild the APK.
    url: "http://REPLACE_WITH_TAILSCALE_HOSTNAME:3000",
    cleartext: true,
  },
};

export default config;
