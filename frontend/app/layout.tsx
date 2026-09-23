import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans, Source_Sans_3 } from "next/font/google";
import "./globals.css";
import Providers from "./providers";
import { THEME_NO_FLASH_SCRIPT } from "@/lib/themeScript";

/* Two faces, each doing one job: Source Sans 3 for UI/body text (humanist,
 * built for small sizes and dense forms), Plus Jakarta Sans for headings and
 * numerals, where its wider, more geometric shapes give the app a voice of
 * its own. The body face was Inter, which is fine type and also the default
 * every generated UI ships with — the point of changing it is that the app
 * should look chosen rather than scaffolded.
 * Both are variable + latin-subset only, self-hosted by next/font at build
 * time: no runtime request to Google, which also matters here because the
 * app is served over a private Tailscale hostname. */
const sans = Source_Sans_3({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  display: "swap",
  weight: ["600", "700", "800"],
  variable: "--font-display",
});

export const metadata: Metadata = {
  title: "JobPilot",
  description: "Tu asistente personal de búsqueda y aplicación a trabajos.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "JobPilot",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
  /* Per-scheme values so the Android status bar blends into the app's own
     header instead of showing one fixed color against both themes. */
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#10131e" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${sans.variable} ${jakarta.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_NO_FLASH_SCRIPT }} />
      </head>
      <body className="bg-gray-50 font-sans text-gray-900 antialiased dark:bg-gray-950 dark:text-gray-100">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
