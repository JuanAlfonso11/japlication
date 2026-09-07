/**
 * Shared TypeScript types mirroring docs/API_CONTRACT.md.
 * Keep these in sync with the backend contract — this is the single
 * source of truth for shapes used across lib/api.ts and components.
 */

// ---------- Auth ----------

export interface User {
  id: string;
  email: string;
  full_name: string;
  email_verified: boolean;
  email_verified_at?: string | null;
  created_at?: string;
}

export interface ResendVerificationResponse {
  sent: boolean;
  detail: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
}

// ---------- Career Profile (CV Maestro) ----------

export type SkillLevel = "beginner" | "intermediate" | "advanced" | "expert";

export interface Skill {
  name: string;
  category: string;
  level: SkillLevel | string;
  years_experience: number | null;
}

export interface ContactInfo {
  phone: string;
  city: string;
  country: string;
  linkedin: string;
  github: string;
  portfolio: string;
}

export interface ExperienceEntry {
  company: string;
  title: string;
  start_date: string;
  end_date: string | null;
  location: string;
  bullets: string[];
  skills_used: string[];
}

export interface EducationEntry {
  institution: string;
  degree: string;
  field: string;
  start_date: string;
  end_date: string;
}

export interface CertificationEntry {
  name: string;
  issuer: string;
  date: string;
}

export interface LanguageEntry {
  name: string;
  level: string;
}

/** One reusable answer to a question application forms keep asking
 * (work authorization, notice period, salary expectation, ...). Written
 * once in the profile, surfaced per-job in the application kit with a copy
 * button — the repetitive half of applying, which is exactly what the
 * auto-apply products sell, minus any bot answering on your behalf. */
export interface ScreeningAnswer {
  question: string;
  answer: string;
}

/** Seeds for a brand-new answer bank. These are the questions that showed
 * up on essentially every application form reviewed while building this —
 * pre-filling the *questions* (never the answers) means the user is
 * completing a short form instead of facing an empty list and having to
 * remember what gets asked. */
export const COMMON_SCREENING_QUESTIONS: string[] = [
  "¿Tienes autorización para trabajar en el país de la vacante?",
  "¿Requieres patrocinio de visa ahora o en el futuro?",
  "¿Cuál es tu expectativa salarial?",
  "¿Cuál es tu disponibilidad para comenzar / periodo de preaviso?",
  "¿Estás dispuesto a trabajar de forma remota / híbrida / presencial?",
  "¿Cuántos años de experiencia tienes en tu rol principal?",
  "¿Por qué te interesa esta empresa?",
];

export interface CareerProfile {
  id?: string;
  user_id?: string;
  headline: string;
  summary: string;
  contact_info: ContactInfo;
  skills: Skill[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  certifications: CertificationEntry[];
  languages: LanguageEntry[];
  screening_answers: ScreeningAnswer[];
  updated_at?: string;
}

export interface CVUploadResult {
  profile: CareerProfile;
  generated_by: "ai" | "heuristic";
  warnings: string[];
}

export interface ProfileImprovementResult {
  profile: CareerProfile;
  change_log: string[];
  generated_by: "ai" | "manual";
}

// ---------- Jobs ----------

export type ApplicationStatus =
  | "queued"
  | "saved"
  | "passed"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export interface SkillRequirement {
  name: string;
  importance: "required" | "nice_to_have" | string;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  remote_type?: string | null;
  description: string;
  requirements: string[];
  responsibilities?: string[];
  skills_required: SkillRequirement[];
  source_url?: string | null;
  created_at?: string;
  requires_cover_letter?: boolean;
  match?: MatchResult | null;
}

export interface JobImportPayload {
  url: string;
}

export interface JobCreatePayload {
  title: string;
  company: string;
  location: string;
  description: string;
  requirements: string[];
  responsibilities?: string[];
  skills_required: SkillRequirement[];
  source_url?: string | null;
  requires_cover_letter?: boolean;
}

// ---------- External job search (12 providers — GET /jobs/search/aggregate).
// 9 are free/no-auth; adzuna, usajobs and serpapi need API keys set in the
// backend's .env and simply report an error in `sources` (not a hard
// failure) when unconfigured. ----------

export type ExternalProvider =
  | "himalayas"
  | "arbeitnow"
  | "remotive"
  | "jobicy"
  | "remotejobs_org"
  | "themuse"
  | "weworkremotely"
  | "hackernews"
  | "getonbrd"
  | "adzuna"
  | "usajobs"
  | "serpapi";

export const PROVIDER_LABELS: Record<ExternalProvider, string> = {
  himalayas: "Himalayas",
  arbeitnow: "Arbeitnow",
  remotive: "Remotive",
  jobicy: "Jobicy",
  remotejobs_org: "RemoteJobs.org",
  themuse: "The Muse",
  weworkremotely: "We Work Remotely",
  hackernews: "Hacker News",
  getonbrd: "Get on Board",
  adzuna: "Adzuna",
  usajobs: "USAJobs",
  serpapi: "Google Jobs (SerpApi)",
};

export type ExperienceLevel = "internship" | "entry" | "mid" | "senior" | "lead";

export const EXPERIENCE_LEVEL_LABELS: Record<ExperienceLevel, string> = {
  internship: "Practicante / Internship",
  entry: "Junior / Entry level",
  mid: "Nivel medio",
  senior: "Senior",
  lead: "Liderazgo / Management",
};

export type RemoteType = "remote" | "hybrid" | "onsite";

export const REMOTE_TYPE_LABELS: Record<RemoteType, string> = {
  remote: "Remoto",
  hybrid: "Híbrido",
  onsite: "Presencial",
};

// Human-readable location names — mirrors backend `_LOCATION_SLUGS` in
// app/api/v1/routers/jobs.py. Providers that don't recognize a mapped slug
// just skip that filter rather than erroring, so this list can be broader
// than what each individual provider natively understands.
export const LOCATION_OPTIONS: string[] = [
  "United States",
  "Canada",
  "United Kingdom",
  "Europe",
  "Germany",
  "France",
  "Spain",
  "Latin America",
  "Mexico",
  "Brazil",
  "Argentina",
  "Colombia",
  "Chile",
  "Dominican Republic",
  "India",
  "Asia Pacific",
  "Australia",
];

// Job-title dropdown for Discover's search — engineering disciplines plus
// other common job types. Grouped for the <optgroup> UI.
export const JOB_TITLE_GROUPS: { label: string; options: string[] }[] = [
  {
    label: "Ingeniería de software",
    options: [
      "Software Engineer",
      "Frontend Engineer",
      "Backend Engineer",
      "Full Stack Engineer",
      "Mobile Engineer (iOS/Android)",
      "Embedded Software Engineer",
      "Game Developer",
      "QA / Test Engineer",
      "Site Reliability Engineer",
    ],
  },
  {
    label: "Infraestructura y datos",
    options: [
      "DevOps Engineer",
      "Cloud Engineer",
      "Platform Engineer",
      "Data Engineer",
      "Data Scientist",
      "Machine Learning Engineer",
      "AI Engineer",
      "Database Administrator",
      "Security Engineer",
    ],
  },
  {
    label: "Otras ingenierías",
    options: [
      "Electrical Engineer",
      "Mechanical Engineer",
      "Civil Engineer",
      "Industrial Engineer",
      "Chemical Engineer",
      "Systems Engineer",
      "Network Engineer",
      "Hardware Engineer",
      "Biomedical Engineer",
    ],
  },
  {
    label: "Producto y diseño",
    options: ["Product Manager", "Product Designer", "UX Designer", "UI Designer", "UX Researcher"],
  },
  {
    label: "Otros roles",
    options: [
      "Project Manager",
      "Technical Writer",
      "Customer Support",
      "Sales",
      "Marketing",
      "Recruiter / HR",
      "Finance / Accounting",
      "Operations",
    ],
  },
];

export interface ApplyOption {
  title: string;
  link?: string | null;
}

export interface ExternalJobResult {
  external_id: string;
  source: ExternalProvider;
  source_url?: string | null;
  title: string;
  company: string;
  location?: string | null;
  remote_type?: string | null;
  employment_type?: string | null;
  seniority?: string | null;
  description: string;
  requirements: string[];
  responsibilities?: string[];
  skills_required: SkillRequirement[];
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
  posted_at?: string | null;
  posted_at_text?: string | null;
  via?: string | null;
  apply_options?: ApplyOption[];
  thumbnail?: string | null;
}

export interface ExternalJobsSearchResponse {
  provider: ExternalProvider;
  results: ExternalJobResult[];
  next_page_token?: string | null;
  page?: number | null;
  has_more: boolean;
}

export interface ExternalJobImportPayload {
  source: ExternalProvider;
  external_id: string;
}

export interface AggregateSourceStatus {
  provider: ExternalProvider;
  count: number;
  error?: string | null;
}

export interface AggregateSearchResponse {
  results: ExternalJobResult[];
  sources: AggregateSourceStatus[];
}

export interface AutoImportResponse {
  imported: number;
  query?: string | null;
  sources: AggregateSourceStatus[];
}

export interface JobListResponse {
  items: Job[];
  total: number;
}

export interface ApplicationListResponse {
  items: Application[];
  total: number;
}

// ---------- CV Evaluator (profile quality, independent of any job) ----------

export type IssueSeverity = "error" | "warning" | "info";

export interface CVIssue {
  severity: IssueSeverity;
  category: "completeness" | "impact" | "skills_breadth" | "ats_safety" | string;
  message: string;
}

export interface CVCategoryScore {
  score: number;
  issues: CVIssue[];
}

export interface CVEvaluation {
  overall_score: number;
  band: string;
  categories: {
    completeness: CVCategoryScore;
    impact: CVCategoryScore;
    skills_breadth: CVCategoryScore;
    ats_safety: CVCategoryScore;
  };
  top_issues: CVIssue[];
  strengths: string[];
  summary: string;
  summary_generated_by: "ai" | "manual";
}

// ---------- Match Engine ----------

export interface MatchResult {
  overall_score: number;
  technical_score: number;
  experience_score: number;
  semantic_score: number;
  matched_skills: string[];
  missing_skills: string[];
  concerns: string[];
}

// ---------- Interview prep ----------

export type InterviewQuestionCategory = "tecnica" | "brecha" | "requisito" | "empresa";

export interface InterviewQuestion {
  question: string;
  category: InterviewQuestionCategory | string;
  why: string;
  /** Grounded in the profile's own bullets. For a gap these are honest
   * framings rather than answers — the system never invents experience. */
  talking_points: string[];
}

export interface InterviewPrepResponse {
  questions: InterviewQuestion[];
  generated_by: "ai" | "manual";
}

/** One skill that keeps costing points across the jobs the user wanted. */
export interface SkillGap {
  skill: string;
  job_count: number;
  percentage: number;
}

export interface SkillGapsResponse {
  gaps: SkillGap[];
  jobs_considered: number;
  /** Set when there weren't enough saved jobs and the aggregate fell back to
   * every scored posting — a weaker signal, and the UI says so. */
  based_on_all_matches: boolean;
  summary: string | null;
}

// ---------- Applications ----------

export type Decision = "right" | "left";

export interface Application {
  id: string;
  job_id: string;
  user_id?: string;
  status: ApplicationStatus;
  notes?: string | null;
  applied_at?: string | null;
  created_at?: string;
  updated_at?: string;
  job?: Job;
}

export interface DecisionPayload {
  decision: Decision;
  // Set from the job-detail page's "Apply" button once a tailored resume/
  // cover letter has been generated there, so the Application is created
  // with them already attached. Omitted for a plain swipe from Home — a
  // right swipe on a job that requires a cover letter still gets one
  // auto-generated (or reused) server-side either way.
  resume_version_id?: string;
  cover_letter_id?: string;
}

export interface ApplicationUpdatePayload {
  status?: ApplicationStatus;
  notes?: string;
  applied_at?: string | null;
}

// ---------- Resume adaptation ----------

export interface ResumeExperienceEntry {
  company: string;
  title: string;
  start_date?: string | null;
  end_date?: string | null;
  location?: string;
  bullets: string[];
}

export interface ResumeEducationEntry {
  institution: string;
  degree: string;
  field?: string;
  start_date?: string | null;
  end_date?: string | null;
}

export interface ResumeContent {
  summary: string;
  skills: string[];
  experience: ResumeExperienceEntry[];
  education: ResumeEducationEntry[];
}

export interface ResumeVersion {
  id: string;
  user_id: string;
  career_profile_id: string;
  job_id?: string | null;
  title: string;
  content: ResumeContent;
  change_log: string[];
  generated_by: "manual" | "ai";
  /** Null until the user corrects it. An edited version is preferred when a
   * later, similar job looks for a resume to reuse. */
  edited_at?: string | null;
  created_at: string;
  job?: Job | null;
}

export interface ResumeVersionUpdatePayload {
  title?: string;
  content?: {
    summary?: string;
    skills?: string[];
    /** Keyed by the entry's index in `content.experience`. */
    experience_bullets?: Record<number, string[]>;
  };
}

export interface ResumeGeneratePayload {
  tone?: string;
}

export interface ReusableResumeSuggestion {
  resume_version: ResumeVersion | null;
  similarity: number;
  source_job_title?: string | null;
  source_company?: string | null;
}

// ---------- Cover letters ----------

export interface CoverLetter {
  id: string;
  user_id: string;
  job_id: string;
  resume_version_id?: string | null;
  content: string;
  tone: string;
  generated_by: "manual" | "ai";
  created_at: string;
  job?: Job | null;
}

export interface CoverLetterGeneratePayload {
  tone?: string;
  resume_version_id?: string;
}

// ---------- Errors ----------

export interface ApiErrorShape {
  detail: string;
  code?: string;
}

// ---------- Android in-app update check ----------

export interface AndroidUpdateInfo {
  version_code: number | null;
  version_name: string | null;
  apk_url: string | null;
  notes: string | null;
}

// ---------- System status (background job heartbeats) ----------

export interface HeartbeatInfo {
  job_name: string;
  last_run_at: string;
  last_status: string;
  detail: string | null;
}

// ---------- Error log ----------

/** One recorded failure, from either side of the app. The request body is
 * never captured — see db/schema.sql for why. */
export interface ErrorLogEntry {
  id: string;
  /** Short id echoed to the user in the error message, so a report of
   * "salió el código a1b2c3" maps straight to this row. */
  request_id: string;
  source: "backend" | "frontend";
  level: string;
  kind?: string | null;
  message: string;
  stack?: string | null;
  method?: string | null;
  path?: string | null;
  status_code?: number | null;
  user_agent?: string | null;
  url?: string | null;
  created_at: string;
}
