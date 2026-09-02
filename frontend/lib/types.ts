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
  created_at?: string;
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

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  requirements: string[];
  responsibilities?: string[];
  skills: string[];
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
  skills: string[];
  source_url?: string | null;
}

export interface JobListResponse {
  items: Job[];
  total: number;
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
