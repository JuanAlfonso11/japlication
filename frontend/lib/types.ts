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
  updated_at?: string;
}

export interface CVUploadResult {
  profile: CareerProfile;
  generated_by: "ai" | "heuristic";
  warnings: string[];
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
}

// ---------- External job search (6 free, no-auth APIs — GET /jobs/search/aggregate) ----------

export type ExternalProvider =
  | "himalayas"
  | "arbeitnow"
  | "remotive"
  | "jobicy"
  | "remotejobs_org"
  | "themuse";

export const PROVIDER_LABELS: Record<ExternalProvider, string> = {
  himalayas: "Himalayas",
  arbeitnow: "Arbeitnow",
  remotive: "Remotive",
  jobicy: "Jobicy",
  remotejobs_org: "RemoteJobs.org",
  themuse: "The Muse",
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
  created_at: string;
}

export interface ResumeGeneratePayload {
  tone?: string;
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
