import type { CareerProfile } from "@/lib/types";

/** The user's own wording, kept so "Mejorar CV" is undoable. */
export type ImproveSnapshot = Pick<CareerProfile, "headline" | "summary" | "experience">;

export type ImproveNotice = {
  changeLog: string[];
  generatedBy: string;
  /** Both null until the profile is saved: the score is computed server-side
   *  from the saved profile, so there is nothing honest to show before that. */
  scoreBefore: number | null;
  scoreAfter: number | null;
};

export type ImproveState = {
  running: boolean;
  error: string | null;
  notice: ImproveNotice | null;
  /** The rewrite is in the form but not in the database yet; the next save
   *  has to fetch the new score to close the before/after. */
  pendingSave: boolean;
  /** Score of the profile as the user wrote it, read before the rewrite. */
  baselineScore: number | null;
  original: ImproveSnapshot | null;
};

export const initialImproveState: ImproveState = {
  running: false,
  error: null,
  notice: null,
  pendingSave: false,
  baselineScore: null,
  original: null,
};

export type ImproveAction =
  | { type: "start"; snapshot: ImproveSnapshot | null; currentScore: number | null }
  | { type: "succeeded"; changeLog: string[]; generatedBy: string }
  | { type: "failed"; message: string }
  | { type: "scored"; scoreAfter: number | null }
  | { type: "reverted" };

/**
 * "Mejorar CV" moves six things at once — a spinner, an error, a change log,
 * a "still needs saving" flag, the score to compare against and the snapshot
 * to go back to — and every one of them has to move with the others or the
 * card starts lying. Six separate `useState` calls in the page meant six
 * places to remember, and two of them were already being missed:
 *
 *  - Pressing "Mejorar CV" a second time without saving overwrote the
 *    snapshot with the text the AI had just produced. From then on
 *    "Restaurar mi versión" restored the first rewrite, not the user's
 *    writing, while the card kept promising otherwise. The snapshot is now
 *    taken only when no rewrite is already on screen, which is exactly what
 *    the card says: your version is held until you leave or restore.
 *
 *  - "Restaurar mi versión" cleared the change log and the pending flag but
 *    left the baseline score behind, so the next rewrite could show a
 *    before/after measured against a profile that no longer existed.
 *
 * Keeping the transitions here rather than in the component also makes them
 * testable without rendering anything — see improveState.test.ts.
 */
export function improveReducer(state: ImproveState, action: ImproveAction): ImproveState {
  switch (action.type) {
    case "start":
      return {
        ...state,
        running: true,
        error: null,
        notice: null,
        baselineScore: action.currentScore,
        // Only when there is no rewrite already on screen. A second press
        // must not snapshot the AI's own output over the user's.
        original: state.notice === null && action.snapshot ? action.snapshot : state.original,
      };

    case "succeeded":
      return {
        ...state,
        running: false,
        error: null,
        pendingSave: true,
        notice: {
          changeLog: action.changeLog,
          generatedBy: action.generatedBy,
          scoreBefore: null,
          scoreAfter: null,
        },
      };

    case "failed":
      // The snapshot taken at `start` stays: nothing was rewritten, so it is
      // still the current text, and the next attempt will refresh it anyway.
      return { ...state, running: false, error: action.message };

    case "scored":
      return {
        ...state,
        pendingSave: false,
        notice: state.notice
          ? { ...state.notice, scoreBefore: state.baselineScore, scoreAfter: action.scoreAfter }
          : state.notice,
      };

    case "reverted":
      return { ...initialImproveState };

    default:
      return state;
  }
}
