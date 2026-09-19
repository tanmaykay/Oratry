"use client";

import { formatRecordingTime } from "./media-recorder";
import { useMediaRecorder, type CompletedRecording } from "./use-media-recorder";

export function AudioRecorder({ onRecordingReady, submitting = false }: { onRecordingReady?: (recording: CompletedRecording) => void; submitting?: boolean }) {
  const recorder = useMediaRecorder();
  const isRecording = recorder.status === "recording";
  const isRequesting = recorder.status === "requesting-permission";
  const isUnsupported = !recorder.capability.supported || recorder.status === "unsupported";
  return <div className="recorder" aria-live="polite">
    <span className={isRecording ? "record-dot live" : "record-dot"} /><time>{formatRecordingTime(recorder.elapsedSeconds)}</time>
    <p>{isRecording ? "Recording" : isRequesting ? "Requesting microphone access" : recorder.recording ? "Review your recording" : "When you’re ready"}</p>
    {recorder.error && <p className="recorder-error" role="alert">{recorder.error}</p>}
    {isUnsupported && <p className="recorder-error" role="alert">Audio recording is unavailable in this browser. Use a current browser with microphone access.</p>}
    {!recorder.recording && !isUnsupported && <button className={`record-button ${isRecording ? "stop" : ""}`} disabled={isRequesting || submitting} onClick={isRecording ? recorder.stop : recorder.start} aria-label={isRecording ? "Stop recording" : "Start recording"}><span /></button>}
    {recorder.recording && <div className="recording-review"><audio controls src={recorder.recording.previewUrl}>Your browser cannot play this recording.</audio><div className="recorder-actions"><button className="button secondary" disabled={submitting} onClick={recorder.discard}>Discard</button><button className="button" disabled={submitting} onClick={() => { if (recorder.recording) onRecordingReady?.(recorder.recording); }}>{submitting ? "Uploading…" : "Use this recording"}</button></div></div>}
    {!recorder.recording && <small>{isRecording ? "Tap to finish" : isUnsupported ? "Recording is not supported here" : "Selecting start asks for microphone permission. Your audio stays on this device until you choose Use this recording."}</small>}
  </div>;
}
