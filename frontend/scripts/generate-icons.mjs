/** Renders every JobPilot icon from one source of truth: the compass mark
 * defined below, which is the same geometry as `components/ui/Logo.tsx`.
 *
 * Before this existed the icons were hand-made PNGs committed straight to
 * the repo, so a palette change meant either redrawing them by hand or
 * leaving them on the old brand. That is exactly what happened — the app
 * went graphite while the launcher, the PWA and the desktop shortcut all
 * stayed violet. Now `npm run icons` re-renders all of them.
 *
 * Run from `frontend/`:  npm run icons
 * Then, for the Android launcher:  npx capacitor-assets generate --android
 *
 * Colors track `tailwind.config.ts`: graphite body, silver accents. The
 * gradient stops deliberately stay dark — the mark is white, and a
 * gradient that reached brand-200 silver at one corner would leave the
 * ring nearly invisible there.
 */

import { Buffer } from "node:buffer";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = join(HERE, "..");
const REPO = join(FRONTEND, "..");

const SILVER = "#cdd0d6"; // brand-200
const GRADIENT_FROM = "#4f4f57";
const GRADIENT_TO = "#101014";
const SPLASH_LIGHT = "#f5f6f7"; // brand-50
const SPLASH_DARK = "#0e0e10"; // brand-900

/* The tile's gradient, on the dark launch screen only. Rendering the
 * standard tile there produced a near-invisible smudge, and the reason is
 * arithmetic rather than taste: the gradient ends at #101014 while the
 * dark ground is #0e0e10 — the same value — so the bottom half of the
 * tile had nothing to sit against. Lifting the tile up the ramp is the
 * same inversion the primary button already uses in dark mode. */
const GRADIENT_FROM_ON_DARK = "#5e5e68";
const GRADIENT_TO_ON_DARK = "#2b2b31";

/* The mark, in Logo.tsx's 48-unit space. Kept character-identical to the
 * component so the header logo and the launcher icon can never drift. */
const MARK = `
    <circle cx="24" cy="24" r="16" fill="none" stroke="${SILVER}" stroke-width="2.5" opacity="0.5" />
    <path d="M32.08 15.92 L27.23 27.23 L20.77 20.77 Z" fill="#ffffff" />
    <path d="M15.92 32.08 L27.23 27.23 L20.77 20.77 Z" fill="${SILVER}" fill-opacity="0.45" />`;

const gradientDef = (from, to) => `
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${from}" />
      <stop offset="1" stop-color="${to}" />
    </linearGradient>
  </defs>`;

/** The app tile: gradient body plus the mark.
 *
 * `radius` is in 48-unit space (13 matches Logo.tsx). Pass 0 for the
 * maskable and adaptive variants, where the launcher applies its own mask
 * and a pre-rounded corner would show as a dark notch inside it.
 *
 * `markScale` shrinks the mark toward the centre for maskable output,
 * whose safe zone is only the middle ~80% of the canvas. */
function tileSvg({ size, radius = 13, markScale = 1, from = GRADIENT_FROM, to = GRADIENT_TO }) {
  const offset = (48 - 48 * markScale) / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 48 48">
  ${gradientDef(from, to)}
  <rect width="48" height="48" rx="${radius}" fill="url(#g)" />
  <g transform="translate(${offset} ${offset}) scale(${markScale})">${MARK}
  </g>
</svg>`;
}

/** Android's adaptive-icon foreground: the mark alone on transparency.
 * The launcher composites it over the background layer itself. */
function foregroundSvg({ size }) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 48 48">${MARK}
</svg>`;
}

/** Android's adaptive-icon background layer: the gradient, no mark, no
 * rounding — the launcher masks it to whatever shape the device uses. */
function backgroundSvg({ size }) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 48 48">
  ${gradientDef(GRADIENT_FROM, GRADIENT_TO)}
  <rect width="48" height="48" fill="url(#g)" />
</svg>`;
}

/** Launch screen: a flat ground with the tile floating at the centre, at
 * the same proportion Capacitor's generated splashes already used. */
function splashSvg({ size, background, from = GRADIENT_FROM, to = GRADIENT_TO }) {
  const tile = Math.round(size * 0.172);
  const at = Math.round((size - tile) / 2);
  const inner = tileSvg({ size: tile, from, to })
    .replace(/^<svg[^>]*>/, "")
    .replace(/<\/svg>$/, "");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="${background}" />
  <g transform="translate(${at} ${at})">
    ${inner}
  </g>
</svg>`;
}

const png = (svg) => sharp(Buffer.from(svg)).png().toBuffer();

/** Assembles a real multi-resolution .ico.
 *
 * Windows shortcuts ask for 16/32/48/256 depending on the view, and the
 * previous .ico held a single 32x32 frame (System.Drawing's GetHicon
 * always yields 32x32, whatever the source PNG's size), so the desktop
 * icon was upscaled and blurry in anything but the smallest list view.
 *
 * The format is a 6-byte header, one 16-byte directory entry per frame,
 * then the frames themselves. Modern Windows accepts PNG-compressed
 * frames directly, which is why no BMP encoding is needed here. */
function buildIco(frames) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // 1 = icon
  header.writeUInt16LE(frames.length, 4);

  let offset = 6 + frames.length * 16;
  const entries = frames.map(({ size, data }) => {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(size >= 256 ? 0 : size, 0); // 0 means 256
    entry.writeUInt8(size >= 256 ? 0 : size, 1);
    entry.writeUInt8(0, 2); // palette size
    entry.writeUInt8(0, 3); // reserved
    entry.writeUInt16LE(1, 4); // colour planes
    entry.writeUInt16LE(32, 6); // bits per pixel
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += data.length;
    return entry;
  });

  return Buffer.concat([header, ...entries, ...frames.map((f) => f.data)]);
}

function write(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, data);
  console.log(`  ${path.replace(REPO, ".")}  ${(data.length / 1024).toFixed(1)} kB`);
}

const targets = [
  // Capacitor sources — `npx capacitor-assets generate --android` turns
  // these into every mipmap and splash density.
  ["resources/icon.png", () => png(tileSvg({ size: 1024 }))],
  ["resources/icon-foreground.png", () => png(foregroundSvg({ size: 1024 }))],
  ["resources/icon-background.png", () => png(backgroundSvg({ size: 1024 }))],
  ["resources/splash.png", () => png(splashSvg({ size: 2732, background: SPLASH_LIGHT }))],
  [
    "resources/splash-dark.png",
    () =>
      png(
        splashSvg({
          size: 2732,
          background: SPLASH_DARK,
          from: GRADIENT_FROM_ON_DARK,
          to: GRADIENT_TO_ON_DARK,
        })
      ),
  ],

  // PWA / "Add to Home Screen", and the source the desktop shortcut reads.
  ["public/icons/icon-192.png", () => png(tileSvg({ size: 192 }))],
  ["public/icons/icon-512.png", () => png(tileSvg({ size: 512 }))],
  ["public/icons/icon-192-maskable.png", () => png(tileSvg({ size: 192, radius: 0, markScale: 0.8 }))],
  ["public/icons/icon-512-maskable.png", () => png(tileSvg({ size: 512, radius: 0, markScale: 0.8 }))],
  ["public/icons/apple-touch-icon.png", () => png(tileSvg({ size: 180 }))],
];

console.log("Rendering icons...");
for (const [relative, render] of targets) {
  write(join(FRONTEND, relative), await render());
}

const icoSizes = [16, 32, 48, 64, 128, 256];
const frames = await Promise.all(
  icoSizes.map(async (size) => ({ size, data: await png(tileSvg({ size })) }))
);
write(join(REPO, "scripts", ".icon", "jobpilot.ico"), buildIco(frames));

console.log("\nDone. Next: npx capacitor-assets generate --android");
