export const RECORDING_MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"] as const;

export function selectRecordingMimeType(mediaRecorder: Pick<typeof MediaRecorder, "isTypeSupported"> | undefined): string | null {
  if (!mediaRecorder) return null;
  return RECORDING_MIME_TYPES.find((mimeType) => mediaRecorder.isTypeSupported(mimeType)) ?? null;
}

export function getRecordingCapability() {
  if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return { supported: false, mimeType: null };
  return { supported: true, mimeType: selectRecordingMimeType(window.MediaRecorder) };
}

export function formatRecordingTime(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(safeSeconds / 60)}:${String(safeSeconds % 60).padStart(2, "0")}`;
}
