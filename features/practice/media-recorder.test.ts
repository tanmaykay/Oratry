import { describe, expect, it } from "vitest";
import { formatRecordingTime, selectRecordingMimeType } from "./media-recorder";
import { isCurrentRecordingGeneration } from "./use-media-recorder";

describe("media recorder helpers", () => {
  it("selects the first supported recording format", () => {
    expect(selectRecordingMimeType({ isTypeSupported: (type) => type === "audio/webm" })).toBe("audio/webm");
  });
  it("returns null when no supported format is available", () => {
    expect(selectRecordingMimeType({ isTypeSupported: () => false })).toBeNull();
  });
  it("formats elapsed time defensively", () => {
    expect(formatRecordingTime(125.9)).toBe("2:05");
    expect(formatRecordingTime(-1)).toBe("0:00");
  });
  it("rejects delayed callbacks from a previous recording generation", () => {
    expect(isCurrentRecordingGeneration(4, 5)).toBe(false);
    expect(isCurrentRecordingGeneration(5, 5)).toBe(true);
  });
});
