"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getRecordingCapability } from "./media-recorder";

export type RecorderStatus = "idle" | "requesting-permission" | "recording" | "stopped" | "unsupported" | "error";
export type CompletedRecording = { blob: Blob; durationSeconds: number; mimeType: string; previewUrl: string };
type MediaRecorderError = { error?: { message?: string } };

export function isCurrentRecordingGeneration(generation: number, currentGeneration: number): boolean {
  return generation === currentGeneration;
}

function stopTracks(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}

function recorderErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") return "Microphone permission was denied. Allow access and try again.";
    if (error.name === "NotFoundError") return "No microphone was found. Connect one and try again.";
    if (error.name === "NotReadableError") return "Your microphone is busy in another application. Close it and try again.";
    return error.message || "We could not access your microphone.";
  }
  return "Recording could not start. Please try again.";
}

export function useMediaRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [recording, setRecording] = useState<CompletedRecording | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const generationRef = useRef(0);
  const capability = useMemo(() => getRecordingCapability(), []);

  const discard = useCallback(() => {
    // Invalidating first prevents delayed callbacks from this recorder changing a later session.
    generationRef.current += 1;
    const mediaRecorder = mediaRecorderRef.current;
    const stream = streamRef.current;
    mediaRecorderRef.current = null;
    streamRef.current = null;
    if (mediaRecorder?.state === "recording") mediaRecorder.stop();
    stopTracks(stream);
    startedAtRef.current = null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setRecording(null);
    setElapsedSeconds(0);
    setError(null);
    setStatus(capability.supported ? "idle" : "unsupported");
  }, [capability.supported]);

  const start = useCallback(async () => {
    if (!capability.supported) {
      setStatus("unsupported");
      setError("This browser does not support audio recording. Use a current browser with microphone access.");
      return;
    }
    discard();
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    setStatus("requesting-permission");
    let acquiredStream: MediaStream | null = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      acquiredStream = stream;
      if (!isCurrentRecordingGeneration(generation, generationRef.current)) {
        stopTracks(stream);
        return;
      }
      const mediaRecorder = new MediaRecorder(stream, capability.mimeType ? { mimeType: capability.mimeType } : undefined);
      const chunks: Blob[] = [];
      const startedAt = Date.now();
      streamRef.current = stream;
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => { if (event.data.size > 0) chunks.push(event.data); };
      mediaRecorder.onerror = (event: MediaRecorderError) => {
        if (!isCurrentRecordingGeneration(generation, generationRef.current)) return;
        stopTracks(stream);
        if (streamRef.current === stream) streamRef.current = null;
        if (mediaRecorderRef.current === mediaRecorder) mediaRecorderRef.current = null;
        setStatus("error");
        setError(event.error?.message || "Recording stopped unexpectedly. Please try again.");
      };
      mediaRecorder.onstop = () => {
        if (!isCurrentRecordingGeneration(generation, generationRef.current)) return;
        const mimeType = mediaRecorder.mimeType || capability.mimeType || "audio/webm";
        const blob = new Blob(chunks, { type: mimeType });
        const durationSeconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
        stopTracks(stream);
        if (streamRef.current === stream) streamRef.current = null;
        if (mediaRecorderRef.current === mediaRecorder) mediaRecorderRef.current = null;
        if (blob.size === 0) {
          setStatus("error");
          setError("No audio was captured. Check your microphone and try again.");
          return;
        }
        const previewUrl = URL.createObjectURL(blob);
        previewUrlRef.current = previewUrl;
        setRecording({ blob, durationSeconds, mimeType, previewUrl });
        setElapsedSeconds(durationSeconds);
        setStatus("stopped");
      };
      startedAtRef.current = startedAt;
      setElapsedSeconds(0);
      mediaRecorder.start();
      setStatus("recording");
    } catch (caught) {
      if (!isCurrentRecordingGeneration(generation, generationRef.current)) {
        stopTracks(acquiredStream);
        return;
      }
      stopTracks(acquiredStream);
      stopTracks(streamRef.current);
      streamRef.current = null;
      mediaRecorderRef.current = null;
      setStatus("error");
      setError(recorderErrorMessage(caught));
    }
  }, [capability, discard]);

  const stop = useCallback(() => { if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop(); }, []);

  useEffect(() => {
    if (status !== "recording") return;
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - (startedAtRef.current ?? Date.now())) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [status]);
  useEffect(() => () => {
    generationRef.current += 1;
    const mediaRecorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;
    if (mediaRecorder?.state === "recording") mediaRecorder.stop();
    stopTracks(streamRef.current);
    streamRef.current = null;
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  return { capability, discard, elapsedSeconds, error, recording, start, status, stop };
}
