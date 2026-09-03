import { jobsApi } from "./api";
import type { Job } from "./types";

/** After creating/importing a job, immediately compute its match score so it
 * shows up in the home swipe queue right away instead of silently sitting
 * unmatched until someone happens to open it. */
export async function importAndMatch(job: Job): Promise<Job> {
  try {
    const match = await jobsApi.match(job.id);
    return { ...job, match };
  } catch {
    // Non-fatal — the job is still saved; it'll get matched the first time
    // its detail page or the swipe queue asks for it.
    return job;
  }
}
