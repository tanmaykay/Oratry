import { describe, expect, it } from "vitest";
import { result } from "./mock-data";
describe("mock analysis result", () => {
  it("contains a primary coaching focus and complete scorecard", () => {
    expect(result.focus.skill).toBe("Fluency");
    expect(result.overall).toBeGreaterThan(0);
    expect(Object.keys(result.scores)).toHaveLength(6);
  });
});
