import type {
  ApiErrorShape,
  Application,
  ApplicationUpdatePayload,
  AuthResponse,
  CareerProfile,
  CoverLetter,
  CVEvaluation,
  CoverLetterGeneratePayload,
  DecisionPayload,
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
  ResumeGeneratePayload,
  ResumeVersion,
  UpworkAuthorizeResponse,
  UpworkStatus,
  User,
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const TOKEN_KEY = "jobflow_token";

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

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, query } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (auth) {
    const token = getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Could not reach the JobFlow AI server. Check your connection and try again."
    );
  }

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

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// ---------- Auth ----------

export const authApi = {
  register: (payload: RegisterPayload) =>
    request<AuthResponse>("/auth/register", { method: "POST", body: payload, auth: false }),
  login: (payload: LoginPayload) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: payload, auth: false }),
  me: () => request<User>("/auth/me"),
};

// ---------- Career Profile ----------

export const profileApi = {
  get: () => request<CareerProfile>("/profile"),
  save: (payload: CareerProfile) =>
    request<CareerProfile>("/profile", { method: "PUT", body: payload }),
  evaluation: () => request<CVEvaluation>("/profile/evaluation"),
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
  generateCoverLetter: (id: string, payload?: CoverLetterGeneratePayload) =>
    request<CoverLetter>(`/jobs/${id}/cover-letter`, { method: "POST", body: payload ?? {} }),
  search: (params: {
    provider: ExternalProvider;
    q?: string;
    location?: string;
    country?: string;
    worldwide?: boolean;
    seniority?: string;
    employment_type?: string;
    sort?: string;
    page?: number;
    next_page_token?: string;
  }) => request<ExternalJobsSearchResponse>("/jobs/search", { query: params }),
  importExternal: (payload: ExternalJobImportPayload) =>
    request<Job>("/jobs/search/import", { method: "POST", body: payload }),
};

// ---------- Integrations (Upwork OAuth) ----------

export const integrationsApi = {
  upworkStatus: () => request<UpworkStatus>("/integrations/upwork/status"),
  upworkAuthorize: () => request<UpworkAuthorizeResponse>("/integrations/upwork/authorize"),
  upworkDisconnect: () => request<void>("/integrations/upwork", { method: "DELETE" }),
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
};

export const coverLetterApi = {
  get: (id: string) => request<CoverLetter>(`/cover-letters/${id}`),
};
