"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api, type AnalysisResultResponse, type AttemptResponse, type ComparisonResponse, type PlaybackResponse, type TranscriptWord } from "../shared/api/client";
import { Button, Card, Eyebrow, Score } from "../ui/primitives";
import type { View } from "../ui/shell";

const fillers = new Set(["um", "uh", "umm", "uhh", "er", "erm", "ah", "hmm", "like"]);
const displayName = (name: string) => name.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
const displayValue = (value: unknown) => typeof value === "number" ? (Number.isInteger(value) ? String(value) : value.toFixed(1)) : Array.isArray(value) ? value.join(", ") || "None" : String(value ?? "Unavailable");
const timestamp = (seconds: number | null) => seconds == null ? "timestamp unavailable" : `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

function words(result: AnalysisResultResponse): TranscriptWord[] {
  return result.transcript.segments.flatMap(segment => segment.words);
}

function annotatedTranscript({ result }: { result: AnalysisResultResponse }) {
  const allWords = words(result);
  const items = result.objectiveMetrics.items;
  const repeated = new Set<string>(Array.isArray(items.find(item => item.name === "immediate_repetitions")?.value) ? items.find(item => item.name === "immediate_repetitions")?.value as string[] : []);
  const corrections = new Set<number>(Array.isArray(items.find(item => item.name === "possible_self_correction_positions")?.value) ? items.find(item => item.name === "possible_self_correction_positions")?.value as number[] : []);
  if (!allWords.length) return <p>{result.transcript.text}</p>;
  return <p className="annotated-transcript">{allWords.map((item, index) => {
    const normalized = item.normalized_word.toLowerCase(); const tags = [fillers.has(normalized) && "filler", repeated.has(normalized) && "repeat", corrections.has(index) && "correction"].filter(Boolean).join(" ");
    const confidence = item.confidence == null ? "confidence unavailable" : `${Math.round(item.confidence * 100)}% transcription confidence`;
    return <span key={`${index}-${item.start_time ?? "unknown"}`} className={tags} title={`${timestamp(item.start_time)} · ${confidence}`}>{item.word}{" "}</span>;
  })}</p>;
}

export function Results({ go, token, attemptId, onRetry }: { go: (v: View) => void; token: string; attemptId: string | null; onRetry: (attemptId: string, attempt: AttemptResponse) => void }) {
  const [result, setResult] = useState<AnalysisResultResponse | null>(null); const [playback, setPlayback] = useState<PlaybackResponse | null>(null); const [reviewAttempt, setReviewAttempt] = useState<AttemptResponse | null>(null); const [comparison, setComparison] = useState<ComparisonResponse | null>(null); const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { if (!attemptId) return; setError(null); try { const [analysis, attempt, audio, comparisonResult] = await Promise.all([api.result(token, attemptId), api.attempt(token, attemptId), api.playback(token, attemptId).catch(cause => cause instanceof ApiError && cause.code === "recording_unavailable" ? null : Promise.reject(cause)), api.comparison(token, attemptId).catch(cause => cause instanceof ApiError && cause.code === "comparison_not_available" ? null : Promise.reject(cause))]); setResult(analysis); setReviewAttempt(attempt); setPlayback(audio); setComparison(comparisonResult); } catch (cause) { setError(cause instanceof ApiError ? cause.message : "We couldn't load this recording review."); } }, [attemptId, token]);
  useEffect(() => { void load(); }, [load]);
  const facts = useMemo(() => result?.objectiveMetrics.items.filter(item => item.measurement_kind === "deterministic" || item.source !== undefined) ?? [], [result]);
  if (!attemptId) return <div className="page narrow"><h1>Select a completed practice</h1><Button onClick={() => go("progress")}>Open progress</Button></div>;
  if (error) return <div className="page narrow"><h1>Review unavailable</h1><p role="alert">{error}</p><Button onClick={() => void load()}>Try again</Button></div>;
  if (!result) return <div className="processing narrow"><div className="orb" /><p>Loading your recording review…</p></div>;
  const evaluation = result.evaluation.result; const overall = result.scorecard.overall ?? 0;
  return <div className="page results"><Eyebrow>Challenge review · {reviewAttempt ? `${Math.round(reviewAttempt.challenge.targetDurationSeconds / 60)} minute target` : "Completed attempt"}</Eyebrow><div className="result-head"><div><h1>{evaluation.primary_weakness.dimension === "structure" ? "Make the shape clearer." : "Build on this attempt."}</h1><p>{reviewAttempt?.challenge.prompt}</p></div><Score value={overall} /></div>
    <section className="split-section"><div><Eyebrow>Listen back</Eyebrow><h2>Your recording</h2><p className="muted">Private playback is available only until raw-audio retention ends.</p></div><Card>{playback ? <audio className="recording-player" controls preload="metadata" src={playback.url}>Your browser does not support audio playback.</audio> : <p>Audio is no longer available, but your transcript and analysis remain.</p>}</Card></section>
    <section className="split-section"><div><Eyebrow>Challenge evidence</Eyebrow><h2>What we measured</h2><p className="muted">These are deterministic transcript-derived facts, not personality judgments.</p></div><div className="metric-grid">{facts.map(metric => <Card key={metric.name}><span>{displayName(metric.name)}</span><strong>{displayValue(metric.value)}</strong><small>{metric.note ?? metric.unit ?? "Measured from this attempt"}</small></Card>)}</div></section>
    <section className="split-section interpretation"><div><Eyebrow>Coaching for this challenge</Eyebrow><h2>One focus for your retry</h2><p className="muted">The interpretation is tied to this prompt, target skills, transcript, and measured facts.</p></div><Card><h2>{evaluation.primary_weakness.observation}</h2><p>{evaluation.primary_weakness.explanation}</p><hr /><strong>Your next action</strong><p>{evaluation.recommendation.action}</p><strong>Success looks like</strong><p>{evaluation.recommendation.success_criterion}</p></Card></section>
    <section className="split-section interpretation"><div><Eyebrow>Dimension review</Eyebrow><h2>How the response met the challenge</h2></div><Card><div className="score-bars">{Object.entries(evaluation.dimensions).map(([skill, value]) => <div key={skill}><span>{skill}</span><i><b style={{ width: `${value.score}%` }} /></i><strong>{value.score}</strong></div>)}</div></Card></section>
    <section className="transcript"><Eyebrow>Timestamped transcript</Eyebrow>{annotatedTranscript({ result })}<div className="annotation-key"><span className="filler">Filler word</span><span className="repeat">Immediate repetition</span><span className="correction">Possible self-correction</span></div><p className="muted">Annotations are lexical heuristics from the transcript. They are not a diagnosis of stuttering, nervousness, or confidence.</p></section>
    {comparison && <section className="split-section"><div><Eyebrow>Same-challenge comparison</Eyebrow><h2>What changed</h2><p className="muted">Both columns use persisted evidence and the same challenge.</p></div><Card className="comparison-table"><div className="comparison-head"><span>Measure</span><span>Original</span><span>Retry</span></div><div><strong>Overall score</strong><span>{comparison.original.overallScore ?? "Unavailable"}</span><span>{comparison.retry.overallScore ?? "Unavailable"}</span></div>{comparison.original.metrics.map(metric => <div key={metric.name}><strong>{displayName(metric.name)}</strong><span>{displayValue(metric.value)}</span><span>{displayValue(comparison.retry.metrics.find(candidate => candidate.name === metric.name)?.value)}</span></div>)}</Card></section>}
    <div className="actions"><Button disabled={!reviewAttempt} onClick={() => reviewAttempt && onRetry(attemptId, reviewAttempt)}>Retry this challenge <span>→</span></Button><Button variant="secondary" onClick={() => go("progress")}>Review progress</Button></div></div>;
}

export function Feedback({ go }: { go: (v: View) => void }) { return <div className="page feedback narrow"><Eyebrow>One focus for next time</Eyebrow><h1>Keep the evidence<br /><i>in view.</i></h1><p>Use the completed review to choose one behavior for the retry.</p><Button onClick={() => go("progress")}>Open your review</Button></div>; }
export function Retry({ go }: { go: (v: View) => void }) { return <div className="page retry narrow"><Eyebrow>Retry challenge</Eyebrow><h1>Retry from the<br /><i>review.</i></h1><p>Start the same assigned challenge from your result review so the comparison remains honest.</p><Button onClick={() => go("results")}>Return to review</Button></div>; }
export function Comparison({ go }: { go: (v: View) => void }) { return <div className="page comparison"><Eyebrow>Challenge comparison</Eyebrow><h1>Compare real<br /><i>evidence.</i></h1><p>Comparison becomes available after two completed attempts of the same challenge.</p><Button onClick={() => go("progress")}>See attempts</Button></div>; }
