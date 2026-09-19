export async function sha256Hex(blob: Blob): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error("Secure hashing is unavailable in this browser. Use a current browser over HTTPS.");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function uploadErrorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "Your recording could not be uploaded. Try again.";
}
