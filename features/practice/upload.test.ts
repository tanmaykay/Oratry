import { describe, expect, it } from "vitest";
import { sha256Hex, uploadErrorMessage } from "./upload";

describe("recording upload helpers", () => {
  it("hashes exact blob bytes as lowercase SHA-256 hex", async () => {
    await expect(sha256Hex(new Blob(["abc"]))).resolves.toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });

  it("keeps a useful upload error message", () => {
    expect(uploadErrorMessage(new Error("Upload expired"))).toBe("Upload expired");
  });
});
