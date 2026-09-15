import { describe, expect, it } from "vitest";
import {
  improveReducer,
  initialImproveState,
  type ImproveSnapshot,
  type ImproveState,
} from "./improveState";

const MINE: ImproveSnapshot = {
  headline: "Ingeniero backend",
  summary: "Lo que yo escribí.",
  experience: [],
};

const AI: ImproveSnapshot = {
  headline: "Senior Backend Engineer | Python & Distributed Systems",
  summary: "Lo que escribió la IA.",
  experience: [],
};

/** Runs a list of actions from a starting state, for readable multi-step tests. */
function run(state: ImproveState, ...actions: Parameters<typeof improveReducer>[1][]): ImproveState {
  return actions.reduce(improveReducer, state);
}

describe("improveReducer", () => {
  it("takes the user's version as the snapshot when the rewrite starts", () => {
    const state = improveReducer(initialImproveState, {
      type: "start",
      snapshot: MINE,
      currentScore: 61,
    });

    expect(state.running).toBe(true);
    expect(state.original).toEqual(MINE);
    expect(state.baselineScore).toBe(61);
  });

  it("keeps the user's version when the rewrite is run a second time", () => {
    // The bug this reducer exists to close: pressing "Mejorar CV" again
    // without saving used to snapshot the AI's own output, so "Restaurar mi
    // versión" restored the first rewrite instead of what the user wrote.
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: ["Reescribió el titular"], generatedBy: "ai" },
      { type: "start", snapshot: AI, currentScore: 61 },
      { type: "succeeded", changeLog: ["Reescribió el resumen"], generatedBy: "ai" }
    );

    expect(state.original).toEqual(MINE);
  });

  it("takes a fresh snapshot once the previous rewrite is no longer on screen", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: [], generatedBy: "ai" },
      { type: "reverted" },
      { type: "start", snapshot: AI, currentScore: 61 }
    );

    expect(state.original).toEqual(AI);
  });

  it("does not erase the snapshot when the profile has not loaded", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "reverted" },
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "start", snapshot: null, currentScore: null }
    );

    expect(state.original).toEqual(MINE);
  });

  it("clears the previous error and change log when a new attempt starts", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: ["algo"], generatedBy: "ai" },
      { type: "failed", message: "No se pudo mejorar el CV." },
      { type: "start", snapshot: MINE, currentScore: 61 }
    );

    expect(state.error).toBeNull();
    expect(state.notice).toBeNull();
  });

  it("marks the rewrite as needing a save, with no score until there is one", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: ["Reescribió el titular"], generatedBy: "ai" }
    );

    expect(state.running).toBe(false);
    expect(state.pendingSave).toBe(true);
    expect(state.notice).toEqual({
      changeLog: ["Reescribió el titular"],
      generatedBy: "ai",
      scoreBefore: null,
      scoreAfter: null,
    });
  });

  it("keeps the snapshot when the rewrite fails", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "failed", message: "No se pudo mejorar el CV." }
    );

    expect(state.running).toBe(false);
    expect(state.error).toBe("No se pudo mejorar el CV.");
    expect(state.original).toEqual(MINE);
    expect(state.pendingSave).toBe(false);
  });

  it("closes the before/after with the score read before the rewrite", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: [], generatedBy: "ai" },
      { type: "scored", scoreAfter: 78 }
    );

    expect(state.pendingSave).toBe(false);
    expect(state.notice?.scoreBefore).toBe(61);
    expect(state.notice?.scoreAfter).toBe(78);
    // The way back survives the save — the card promises it until the user
    // leaves the screen.
    expect(state.original).toEqual(MINE);
  });

  it("shows no score when the save went through but the new score did not", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: [], generatedBy: "ai" },
      { type: "scored", scoreAfter: null }
    );

    expect(state.pendingSave).toBe(false);
    expect(state.notice?.scoreAfter).toBeNull();
  });

  it("restoring leaves nothing behind, baseline score included", () => {
    const state = run(
      initialImproveState,
      { type: "start", snapshot: MINE, currentScore: 61 },
      { type: "succeeded", changeLog: ["algo"], generatedBy: "ai" },
      { type: "reverted" }
    );

    expect(state).toEqual(initialImproveState);
  });
});
