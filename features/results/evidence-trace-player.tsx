"use client";

import { useEffect, useRef, useState } from "react";
import type { PlaybackResponse } from "../shared/api/client";
import { buildWaveformPeaks } from "./waveform";

export type EvidenceMarker = { start: number; end: number; kind: "filler" | "repeat" | "correction"; label: string };

const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export function EvidenceTracePlayer({ source, markers, selectedTime, onSelectTime }: { source: PlaybackResponse; markers: EvidenceMarker[]; selectedTime: number | null; onSelectTime: (time: number) => void }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [peaks, setPeaks] = useState<number[]>([]);
  const [waveformUnavailable, setWaveformUnavailable] = useState(false);
  const [waveformError, setWaveformError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setPeaks([]); setWaveformUnavailable(false); setWaveformError(null); setCurrentTime(0); setDuration(0);
    void (async () => {
      try {
        const response = await fetch(source.url, { signal: controller.signal });
        if (!response.ok) throw new Error("Recording could not be fetched for waveform decoding.");
        const bytes = await response.arrayBuffer();
        const AudioContextConstructor = window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        if (!AudioContextConstructor) throw new Error("Audio decoding is unavailable in this browser.");
        const context = new AudioContextConstructor();
        try {
          const buffer = await context.decodeAudioData(bytes);
          if (!controller.signal.aborted) {
            setPeaks(buildWaveformPeaks(Array.from({ length: buffer.numberOfChannels }, (_, index) => buffer.getChannelData(index))));
            setDuration(previous => previous || buffer.duration);
          }
        } finally { await context.close(); }
      } catch (error) {
        if (!controller.signal.aborted) {
          setWaveformUnavailable(true);
          setWaveformError(error instanceof Error && error.message ? error.message : "The browser could not decode this recording.");
        }
      }
    })();
    return () => controller.abort();
  }, [source.url]);

  useEffect(() => {
    if (selectedTime == null || !audioRef.current || Math.abs(audioRef.current.currentTime - selectedTime) < 0.08) return;
    audioRef.current.currentTime = selectedTime;
    setCurrentTime(selectedTime);
  }, [selectedTime]);

  const seek = (time: number) => {
    const target = Math.min(Math.max(time, 0), duration || time);
    if (audioRef.current) audioRef.current.currentTime = target;
    setCurrentTime(target); onSelectTime(target);
  };
  const togglePlayback = async () => {
    const audio = audioRef.current; if (!audio) return;
    if (audio.paused) { try { await audio.play(); } catch { setIsPlaying(false); } } else audio.pause();
  };
  const seekFromWaveform = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!duration) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    seek(((event.clientX - bounds.left) / bounds.width) * duration);
  };

  return <div className="evidence-trace">
    <audio ref={audioRef} preload="metadata" src={source.url} onLoadedMetadata={event => setDuration(event.currentTarget.duration)} onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)} onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} onEnded={() => setIsPlaying(false)} />
    <div className="evidence-trace-head"><span>Actual recording amplitude</span><small>{formatTime(currentTime)} / {formatTime(duration)}</small></div>
    <div className="waveform" onClick={seekFromWaveform} role="presentation">
      {peaks.length > 0 ? <div className="waveform-bars" aria-hidden="true">{peaks.map((peak, index) => <i key={index} style={{ height: `${peak * 100}%` }} />)}</div> : <div className="waveform-empty" aria-live="polite">{waveformUnavailable ? `Waveform unavailable: ${waveformError}` : "Decoding the recording waveform…"}</div>}
      {duration > 0 && markers.map((marker, index) => <button key={`${marker.kind}-${marker.start}-${index}`} type="button" className={`waveform-marker ${marker.kind}`} style={{ left: `${(marker.start / duration) * 100}%`, width: `${Math.max(((marker.end - marker.start) / duration) * 100, 0.6)}%` }} onClick={event => { event.stopPropagation(); seek(marker.start); }} aria-label={`${marker.label} at ${formatTime(marker.start)}`} title={`${marker.label} · ${formatTime(marker.start)}`} />)}
      {duration > 0 && <i className="waveform-playhead" style={{ left: `${(currentTime / duration) * 100}%` }} aria-hidden="true" />}
    </div>
    <div className="evidence-controls"><button type="button" className="trace-play" onClick={() => void togglePlayback()} aria-label={isPlaying ? "Pause recording" : "Play recording"}>{isPlaying ? "Pause" : "Play"}</button><label><span className="sr-only">Recording position</span><input type="range" min="0" max={duration || 0} step="0.01" value={Math.min(currentTime, duration || 0)} onChange={event => seek(Number(event.target.value))} /></label><span>{waveformUnavailable ? "Playback is still available." : "Select highlighted evidence or transcript words."}</span></div>
    <p className="waveform-note">The waveform shows decoded audio amplitude only. Colored markers identify transcript-derived evidence, not moment-by-moment skill scores.</p>
  </div>;
}
