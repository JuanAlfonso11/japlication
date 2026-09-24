import { ApiError, jobsApi } from "./api";
import type { Job } from "./types";

/** A job just added by the user, and where it ended up. */
export type AddedJob = Job & {
  /** No profile yet: it went straight to the Pipeline instead of the queue. */
  savedToPipeline?: boolean;
};

/** After creating/importing a job, make sure the user can find it again.
 *
 * With a profile, the job gets its match score and shows up in the home
 * swipe queue. Without one there is nothing to score against, and the
 * queue only lists scored jobs — so the job used to vanish: "Agregado ✓"
 * and then nothing anywhere. It is saved to the Pipeline instead, and gets
 * scored when the profile is saved (backend: backfill_missing_matches). */
export async function importAndMatch(job: Job): Promise<AddedJob> {
  if (job.match) return job;
  try {
    const match = await jobsApi.match(job.id);
    return { ...job, match };
  } catch (err) {
    if (err instanceof ApiError && err.status === 400) {
      try {
        await jobsApi.decide(job.id, { decision: "right" });
        return { ...job, savedToPipeline: true };
      } catch {
        // Falls through: the job itself is still stored.
      }
    }
    return job;
  }
}
