import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

describe("private recording upload", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses only the issued method and headers for the object-store PUT", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const blob = new Blob(["recording"], { type: "audio/webm" });
    await api.uploadBlob({ method: "PUT", url: "https://storage.example.test/put", objectKey: "private/user/attempt/raw", expiresAt: "2026-09-19T00:00:00Z", headers: { "Content-Type": "audio/webm", "x-amz-checksum-sha256": "issued-checksum" } }, blob);
    expect(fetch).toHaveBeenCalledWith("https://storage.example.test/put", {
      method: "PUT", headers: { "Content-Type": "audio/webm", "x-amz-checksum-sha256": "issued-checksum" }, body: blob,
    });
  });
});
