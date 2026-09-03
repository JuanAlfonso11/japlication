import type { CapacitorConfig } from "@capacitor/cli";

// JobFlow AI's Android app is a thin native shell — it never bundles the
// web app, it just points the WebView at the live Next.js server (same
// approach as opening the site in a mobile browser, but as an installable
// app with its own icon and no browser chrome). That means:
//   - There's nothing to rebuild the APK for when frontend code changes —
//     only `server.url` itself, native plugins, or the icon ever need a
//     rebuild.
//   - `server.url` MUST be reachable from the phone wherever it's used, not
//     just on the home Wi-Fi. See docs/ANDROID_APP.md — reached over the
//     user's own WireGuard road-warrior VPN (works equally well with
//     Tailscale or any other private VPN back to this LAN), never a public
//     port-forward. The address below is this PC's LAN IP, reachable once
//     the phone is connected to that VPN — it's DHCP-assigned, so if it
//     ever changes (or you'd rather have a fixed reservation), update it
//     here and in android/app/src/main/res/xml/network_security_config.xml.
//   - `cleartext: true` allows plain http:// (not https://) to that host.
//     This is fine specifically because WireGuard traffic is already fully
//     encrypted at the VPN layer between your devices — it never touches
//     the public internet in the clear. Don't point this at a public,
//     non-VPN http:// host.
const config: CapacitorConfig = {
  appId: "ai.jobflow.app",
  appName: "JobFlow AI",
  webDir: "public",
  server: {
    url: "http://10.0.0.232:3000",
    cleartext: true,
  },
};

export default config;
