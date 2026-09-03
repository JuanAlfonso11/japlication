/**
 * Home's "distance slider" is a geographic-scope filter rather than literal
 * distance-in-km math: job postings only carry free-text locations (not
 * coordinates), and several providers are 100%-remote boards with no fixed
 * job location at all, so km-radius filtering isn't reliably computable.
 * Instead this resolves the user's own city/region/country once (via the
 * browser's Geolocation API + OpenStreetMap Nominatim reverse geocoding —
 * free, no API key) and matches it as a substring against each job's
 * location text.
 */

export type GeoScope = "remote" | "city" | "region" | "country" | "any";

export interface UserLocation {
  city?: string;
  region?: string;
  country?: string;
}

export const SCOPE_LEVELS: { scope: GeoScope; label: string }[] = [
  { scope: "remote", label: "Solo remoto" },
  { scope: "city", label: "Mi ciudad" },
  { scope: "region", label: "Mi región" },
  { scope: "country", label: "Mi país" },
  { scope: "any", label: "Cualquier lugar" },
];

const CACHE_KEY = "jobflow_user_location";
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export function loadCachedLocation(): UserLocation | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { location: UserLocation; cachedAt: number };
    if (!parsed.cachedAt || Date.now() - parsed.cachedAt > CACHE_TTL_MS) return null;
    return parsed.location;
  } catch {
    return null;
  }
}

function cacheLocation(location: UserLocation) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify({ location, cachedAt: Date.now() }));
  } catch {
    // Storage might be unavailable (private browsing, quota) — non-fatal,
    // it just means we'll ask again next visit.
  }
}

function getCurrentPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new Error("Tu navegador no soporta geolocalización."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: false,
      timeout: 10000,
      maximumAge: CACHE_TTL_MS,
    });
  });
}

export async function detectUserLocation(): Promise<UserLocation> {
  const position = await getCurrentPosition();
  const { latitude, longitude } = position.coords;

  const res = await fetch(
    `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${latitude}&lon=${longitude}&zoom=10&addressdetails=1`,
    { headers: { Accept: "application/json" } }
  );
  if (!res.ok) throw new Error("No se pudo determinar tu ciudad a partir de tu ubicación.");
  const data = await res.json();
  const address = data.address || {};

  const location: UserLocation = {
    city: address.city || address.town || address.village || address.county || undefined,
    region: address.state || address.region || undefined,
    country: address.country || undefined,
  };
  cacheLocation(location);
  return location;
}

function isRemoteJob(job: { location?: string | null; remote_type?: string | null }): boolean {
  if (job.remote_type === "remote") return true;
  return /remote|remoto|worldwide/i.test(job.location || "");
}

/** Unknown location data never hides a job — same "over-show rather than
 * hide a real match" philosophy used by the backend's experience/remote
 * filters — so a job with no parseable location, or a scope level with no
 * resolved user location yet, always passes rather than disappearing. */
export function jobMatchesScope(
  job: { location?: string | null; remote_type?: string | null },
  scope: GeoScope,
  userLocation: UserLocation | null
): boolean {
  if (scope === "any") return true;

  const remote = isRemoteJob(job);
  if (scope === "remote") return remote;
  if (remote) return true;
  if (!userLocation) return true;

  const haystack = (job.location || "").toLowerCase();
  if (!haystack) return true;

  const needles: (string | undefined)[] =
    scope === "city"
      ? [userLocation.city]
      : scope === "region"
      ? [userLocation.city, userLocation.region]
      : [userLocation.city, userLocation.region, userLocation.country];

  const anyKnown = needles.some(Boolean);
  if (!anyKnown) return true;

  return needles.some((n) => n && haystack.includes(n.toLowerCase()));
}
