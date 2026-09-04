import { describe, expect, it } from "vitest";
import { resolveDragDecision } from "./SwipeCard";

describe("resolveDragDecision", () => {
  it("resolves right past the positive threshold", () => {
    expect(resolveDragDecision(121)).toBe("right");
    expect(resolveDragDecision(700)).toBe("right");
  });

  it("resolves left past the negative threshold", () => {
    expect(resolveDragDecision(-121)).toBe("left");
    expect(resolveDragDecision(-700)).toBe("left");
  });

  it("resolves to no decision inside the threshold (including its exact edges)", () => {
    expect(resolveDragDecision(0)).toBeNull();
    expect(resolveDragDecision(119)).toBeNull();
    expect(resolveDragDecision(-119)).toBeNull();
    expect(resolveDragDecision(120)).toBeNull();
    expect(resolveDragDecision(-120)).toBeNull();
  });
});
