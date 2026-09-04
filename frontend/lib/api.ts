import type {
  AggregateSearchResponse,
  ApiErrorShape,
  Application,
  ApplicationUpdatePayload,
  AutoImportResponse,
  AuthResponse,
  CareerProfile,
  CoverLetter,
  CVEvaluation,
  CoverLetterGeneratePayload,
  DecisionPayload,
  ExperienceLevel,
  RemoteType,
  ExternalJobImportPayload,
  ExternalJobsSearchResponse,
  ExternalProvider,
  Job,
  JobCreatePayload,
  JobImportPayload,
  JobListResponse,
  LoginPayload,
  MatchResult,
  RegisterPayload,
  CVUploadResult,
  ResendVerificationResponse,
  ResumeGeneratePayload,
  ResumeVersion,
  ReusableResumeSuggestion,
  User,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const TOKEN_KEY = "jobflow_token";
const REFRESH_TOKEN_KEY = "jobflow_refresh_token";

/** Fired on `window` when a request's access token turns out to be
 * unrecoverable — invalid/expired AND the background refresh attempt
 * (below) also failed, meaning the session is genuinely over, not just a
 * momentarily-unreachable backend. AuthContext listens for this to clear
 * its React state; storage itself is already cleared by the time it
 * fires. */
export const AUTH_UNAUTHORIZED_EVENT = "jobpilot:unauthorized";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // localStorage unavailable (private mode, etc.) — silently ignore.
  }
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  } catch {
    // localStorage unavailable (private mode, etc.) — silently ignore.
  }
}

/** Error thrown for any non-2xx API response, carrying the parsed detail message. */
export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildQueryString(
  query?: RequestOptions["query"]
): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** No request is allowed to hang forever. Without this, a single stalled
 * connection (Tailscale hiccup, WebView networking glitch, ...) leaves the
 * caller's `pending` state stuck `true` with no error ever thrown — the
 * swipe/decide buttons stay disabled indefinitely with nothing on screen
 * to explain why, since neither the success nor the catch path ever runs. */
const REQUEST_TIMEOUT_MS = 20000;

async function rawFetch(
  path: string,
  method: string,
  body: unknown,
  query: RequestOptions["query"],
  token: string | null
): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "The server took too long to respond. Please try again.");
    }
    throw new ApiError(
      0,
      "Could not reach the JobPilot server. Check your connection and try again."
    );
  } finally {
    clearTimeout(timeout);
  }
}

/** In-flight refresh call, shared by every request that hits a 401 at the
 * same time — without this, N concurrent requests would each try to spend
 * the same (single-use, rotating) refresh token, and only the first would
 * succeed; the rest would wrongly look like the session expired. */
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return null;
    try {
      const res = await rawFetch("/auth/refresh", "POST", { refresh_token: refreshToken }, undefined, null);
      if (!res.ok) return null;
      const data = (await res.json()) as { access_token: string; refresh_token: string };
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      return data.access_token;
    } catch {
      return null;
    }
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const data = text ? safeJsonParse(text) : null;

  if (!res.ok) {
    const shape = (data ?? {}) as Partial<ApiErrorShape>;
    throw new ApiError(
      res.status,
      shape.detail || `Request failed with status ${res.status}`,
      shape.code
    );
  }

  return data as T;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, query } = options;

  const token = auth ? getToken() : null;
  let res = await rawFetch(path, method, body, query, token);

  if (res.status === 401 && auth && token) {
    // The access token is short-lived by design — a 401 on an
    // authenticated request most likely just means it expired, not that
    // the session itself is over. Try a silent refresh and replay the
    // request once before giving up.
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await rawFetch(path, method, body, query, newToken);
    } else {
      // Refresh also failed (refresh token missing/expired/revoked) — the
      // session really is over. Clear storage and let AuthContext know.
      setToken(null);
      setRefreshToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
      }
    }
  }

  return parseResponse<T>(res);
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Like `request`, but sends a multipart/form-data body (a File) instead of
 * JSON — the browser sets its own Content-Type with the boundary, so we
 * must not set one ourselves. Same transparent-refresh-on-401 behavior as
 * `request` — see there for why. */
// Longer than REQUEST_TIMEOUT_MS — this path includes Claude-based PDF
// parsing (profile/import-cv), which legitimately takes longer than a
// normal JSON request.
const UPLOAD_TIMEOUT_MS = 60000;

async function doUpload(path: string, fieldName: string, file: File, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const formData = new FormData();
  formData.append(fieldName, file);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: formData,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "The server took too long to respond. Please try again.");
    }
    throw new ApiError(0, "Could not reach the JobPilot server. Check your connection and try again.");
  } finally {
    clearTimeout(timeout);
  }
}

async function uploadFile<T>(path: string, fieldName: string, file: File): Promise<T> {
  const token = getToken();
  let res = await doUpload(path, fieldName, file, token);

  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await doUpload(path, fieldName, file, newToken);
    } else {
      setToken(null);
      setRefreshToken(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
      }
    }
  }

  return parseResponse<T>(res);
}

// ---------- Auth ----------

export const authApi = {
  register: (payload: RegisterPayload) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: payload, auth: false }),
  login: (payload: LoginPayload) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: payload, auth: false }),
  me: () => request<User>("/auth/me"),
  resendVerification: () =>
    request<ResendVerificationResponse>("/auth/resend-verification", { method: "POST" }),
  // Not used directly by app code (request()/uploadFile() call the raw
  // endpoint themselves to refresh transparently) — exposed for
  // AuthContext.logout(), which revokes the refresh token server-side.
  logout: (refreshToken: string) =>
    request<void>("/auth/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false }),
};

// ---------- Career Profile ----------

export const profileApi = {
  get: () => request<CareerProfile>("/profile"),
  save: (payload: CareerProfile) =>
    request<CareerProfile>("/profile", { method: "PUT", body: payload }),
  evaluation: () => request<CVEvaluation>("/profile/evaluation"),
  importCv: (file: File) => uploadFile<CVUploadResult>("/profile/import-cv", "file", file),
};

// ---------- Jobs ----------

export const jobsApi = {
  import: (payload: JobImportPayload) =>
    request<Job>("/jobs/import", { method: "POST", body: payload }),
  create: (payload: JobCreatePayload) =>
    request<Job>("/jobs", { method: "POST", body: payload }),
  list: (params?: {
    query?: string;
    status?: string;
    min_score?: number;
    limit?: number;
    offset?: number;
  }) => request<JobListResponse>("/jobs", { query: params }),
  get: (id: string) => request<Job>(`/jobs/${id}`),
  remove: (id: string) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  match: (id: string, refresh?: boolean) =>
    request<MatchResult>(`/jobs/${id}/match`, { query: { refresh } }),
  matches: (params?: { min_score?: number; limit?: number; offset?: number }) =>
    request<{ items: Job[]; total: number }>("/matches", { query: params }),
  decide: (id: string, payload: DecisionPayload) =>
    request<Application>(`/jobs/${id}/decision`, { method: "POST", body: payload }),
  generateResume: (id: string, payload?: ResumeGeneratePayload) =>
    request<ResumeVersion>(`/jobs/${id}/resume`, { method: "POST", body: payload ?? {} }),
  reusableResume: (id: string) =>
    request<ReusableResumeSuggestion>(`/jobs/${id}/resume/reusable`),
  generateCoverLetter: (id: string, payload?: CoverLetterGeneratePayload) =>
    request<CoverLetter>(`/jobs/${id}/cover-letter`, { method: "POST", body: payload ?? {} }),
  search: (params: {
    provider: ExternalProvider;
    q?: string;
    location?: string;
    experience_level?: ExperienceLevel;
    remote_type?: RemoteType;
    category?: string;
    country?: string;
    worldwide?: boolean;
    seniority?: string;
    employment_type?: string;
    sort?: string;
    page?: number;
  }) => request<ExternalJobsSearchResponse>("/jobs/search", { query: params }),
  searchAggregate: (params: {
    q?: string;
    location?: string;
    experience_level?: ExperienceLevel;
    remote_type?: RemoteType;
    category?: string;
  }) => request<AggregateSearchResponse>("/jobs/search/aggregate", { query: params }),
  importExternal: (payload: ExternalJobImportPayload) =>
    request<Job>("/jobs/search/import", { method: "POST", body: payload }),
  autoImport: () => request<AutoImportResponse>("/jobs/search/auto-import", { method: "POST" }),
};

// ---------- Applications ----------

export const applicationsApi = {
  list: (status?: string) =>
    request<Application[]>("/applications", { query: { status } }),
  get: (id: string) => request<Application>(`/applications/${id}`),
  update: (id: string, payload: ApplicationUpdatePayload) =>
    request<Application>(`/applications/${id}`, { method: "PATCH", body: payload }),
};

// ---------- Resume / Cover letters ----------

export const resumeApi = {
  get: (id: string) => request<ResumeVersion>(`/resume-versions/${id}`),
  list: () => request<ResumeVersion[]>("/resume-versions"),
};

export const coverLetterApi = {
  get: (id: string) => request<CoverLetter>(`/cover-letters/${id}`),
  list: () => request<CoverLetter[]>("/cover-letters"),
};

// ---------- Push notifications ----------

export const notificationsApi = {
  registerDevice: (token: string, platform: string = "android") =>
    request<void>("/notifications/register-device", { method: "POST", body: { token, platform } }),
  unregisterDevice: (token: string, platform: string = "android") =>
    request<void>("/notifications/register-device", { method: "DELETE", body: { token, platform } }),
};
