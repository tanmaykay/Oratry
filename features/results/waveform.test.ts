import { describe, expect, it } from "vitest";
import { buildWaveformPeaks } from "./waveform";

describe("buildWaveformPeaks", () => {
  it("maps decoded sample amplitude to the corresponding display bars", () => {
    const peaks = buildWaveformPeaks([new Float32Array([0, 0.25, 1, 0])], 4);
    expect(peaks).toEqual([0.035, 0.5, 1, 0.035]);
  });

  it("uses the greatest amplitude across channels", () => {
    const peaks = buildWaveformPeaks([new Float32Array([0.1, 0]), new Float32Array([0, 0.81])], 2);
    expect(peaks[0]).toBeCloseTo(Math.sqrt(0.1));
    expect(peaks[1]).toBeCloseTo(0.9);
  });
});
