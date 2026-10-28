import { describe, expect, it } from "vitest";
import { describeDraft, groupFields, isMoving, minutesFrom, primaryAction } from "./applyDraft";
import type { DraftField } from "./types";

function field(over: Partial<DraftField>): DraftField {
  return {
    key: "k",
    label: "L",
    type: "text",
    required: false,
    section: "main",
    kind: "text",
    options: [],
    value: null,
    display: null,
    source: "none",
    status: "skipped",
    reason: null,
    ...over,
  };
}

const base = { pending_count: 0, handoff_reason: null, error: null, scheduled_for: null, channel: "greenhouse" as const };

describe("describeDraft", () => {
  it("counts what is missing", () => {
    expect(describeDraft({ ...base, status: "needs_user", pending_count: 1 })).toBe(
      "Falta 1 respuesta que solo tú puedes dar."
    );
    expect(describeDraft({ ...base, status: "needs_user", pending_count: 3 })).toMatch(/Faltan 3 respuestas/);
  });

  it("says when a scheduled one goes out", () => {
    const now = new Date("2026-10-27T12:00:00Z");
    const text = describeDraft({ ...base, status: "scheduled", scheduled_for: "2026-10-27T12:09:10Z" }, now);
    expect(text).toContain("en 10 min");
  });

  it("uses the reason the backend gave for a handoff", () => {
    expect(describeDraft({ ...base, status: "handoff", handoff_reason: "CAPTCHA" })).toBe("CAPTCHA");
  });
});

describe("minutesFrom", () => {
  it("rounds up and says now when it is due", () => {
    const now = new Date("2026-10-27T12:00:00Z");
    expect(minutesFrom("2026-10-27T12:00:20Z", now)).toBe("ahora");
    expect(minutesFrom("2026-10-27T12:01:01Z", now)).toBe("en 2 min");
    expect(minutesFrom(null, now)).toBe("en unos minutos");
  });
});

describe("groupFields", () => {
  it("puts required unanswered first, then what the AI wrote", () => {
    const g = groupFields([
      field({ key: "a", required: true, status: "needs_user" }),
      field({ key: "b", status: "filled", source: "ai" }),
      field({ key: "c", status: "filled", source: "profile" }),
      field({ key: "d", status: "skipped" }),
      field({ key: "e", required: true, status: "skipped" }),
    ]);
    expect(g.pending.map((f) => f.key)).toEqual(["a", "e"]);
    expect(g.byAi.map((f) => f.key)).toEqual(["b"]);
    expect(g.filled.map((f) => f.key)).toEqual(["c"]);
    expect(g.skipped.map((f) => f.key)).toEqual(["d"]);
  });
});

describe("status helpers", () => {
  it("knows which states are still moving and what the main action is", () => {
    expect(isMoving("preparing")).toBe(true);
    expect(isMoving("ready")).toBe(false);
    expect(primaryAction({ status: "needs_user", channel: "greenhouse", content: {} })).toBe("answer");
    expect(primaryAction({ status: "scheduled", channel: "greenhouse", content: {} })).toBe("submit");
    expect(primaryAction({ status: "handoff", channel: "external", content: {} })).toBe("open_site");
    expect(primaryAction({ status: "submitted", channel: "email", content: {} })).toBe("none");
  });
});
