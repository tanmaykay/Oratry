"use client";

import { useEffect, useState } from "react";
import { api, type ChallengeAssignment, type UploadAttempt } from "../shared/api/client";
import { Button, Card, Eyebrow } from "../ui/primitives";
import type { View } from "../ui/shell";
import { AudioRecorder } from "./recorder";
import type { CompletedRecording } from "./use-media-recorder";
import { sha256Hex, uploadErrorMessage } from "./upload";

type AssignmentProps = { go: (v: View) => void; assignment: ChallengeAssignment | null };
function AssignmentUnavailable() { return <div className="page narrow"><Eyebrow>Practice</Eyebrow><h1>Your next challenge is loading.</h1><p>Return home and refresh your assignment if this message remains.</p></div>; }
function assignmentTitle(assignment: ChallengeAssignment) { return assignment.reason === "baseline" ? "Baseline challenge" : "Recommended challenge"; }

export function Practice({ go, assignment }: AssignmentProps) {
  if (!assignment) return <AssignmentUnavailable />; const challenge = assignment.challenge;
  return <div className="page"><Eyebrow>Practice</Eyebrow><h1>Your next<br /><i>challenge.</i></h1><div className="challenge-list"><Card className="challenge"><div><span className="pill">{assignment.reason}</span><h2>{assignmentTitle(assignment)}</h2><p>{challenge.prompt}</p><span className="muted">{Math.round(challenge.targetDurationSeconds / 60)} min · {challenge.targetSkills.join(" + ")}</span></div><Button variant="secondary" onClick={() => go("briefing")}>View challenge</Button></Card></div></div>;
}

export function Briefing({ go, assignment }: AssignmentProps) {
  if (!assignment) return <AssignmentUnavailable />; const challenge = assignment.challenge;
  return <div className="page briefing narrow"><button className="back" onClick={() => go("home")}>← Home</button><Eyebrow>{assignmentTitle(assignment)} · version {challenge.version}</Eyebrow><h1>Make your case</h1><p className="prompt">{challenge.prompt}</p><div className="meta-row"><div><span>Target duration</span><strong>{Math.round(challenge.targetDurationSeconds / 60)} minutes</strong></div><div><span>Skills</span><strong>{challenge.targetSkills.join(" · ")}</strong></div></div><Button onClick={() => go("prepare")}>Prepare to speak <span>→</span></Button></div>;
}

export function Preparation({ go, assignment }: AssignmentProps) {
  const [notes, setNotes] = useState(""); if (!assignment) return <AssignmentUnavailable />; const challenge = assignment.challenge;
  return <div className="page preparation"><div className="narrow"><button className="back" onClick={() => go("briefing")}>← Challenge</button><Eyebrow>Take a moment</Eyebrow><h1>Prepare your<br /><i>thinking.</i></h1><p>Use this space to shape your response. These notes are private and won’t be evaluated.</p><ol>{challenge.preparationGuidance.split(/\n|(?<=\.)\s+(?=[A-Z])/).filter(Boolean).map(step => <li key={step}>{step}</li>)}</ol><label className="notes-label">Your notes <span>Optional</span><textarea value={notes} onChange={event => setNotes(event.target.value)} placeholder="A few prompts for yourself…" /></label><Button onClick={() => go("speak")}>I’m ready to speak</Button></div></div>;
}

export function Speaking({ go, assignment, token }: AssignmentProps & { token: string }) {
  const [stage, setStage] = useState<"idle" | "hashing" | "uploading" | "queued" | "error">("idle"); const [error, setError] = useState<string | null>(null); const [pending, setPending] = useState<CompletedRecording | null>(null); const [verifiedUpload, setVerifiedUpload] = useState<{ attempt: UploadAttempt; recording: CompletedRecording } | null>(null); const [queueDurable, setQueueDurable] = useState<boolean | null>(null);
  if (!assignment) return <AssignmentUnavailable />;
  const assignmentId = assignment.assignmentId;
  async function completeVerifiedUpload(value: { attempt: UploadAttempt; recording: CompletedRecording }) {
    setStage("uploading"); setError(null);
    const response = await api.completeUpload(token, value.attempt, value.recording.durationSeconds, value.recording.mimeType, value.recording.blob.size);
    setQueueDurable(response.queue.durable); setStage("queued");
  }
  async function submit(recording: CompletedRecording) {
    setPending(recording); setVerifiedUpload(null); setQueueDurable(null); setError(null); setStage("hashing");
    try {
      const checksumSha256 = await sha256Hex(recording.blob);
      setStage("uploading");
      const attempt = await api.createAttempt(token, assignmentId, recording.mimeType, checksumSha256);
      await api.uploadBlob(attempt.upload, recording.blob);
      const uploaded = { attempt, recording };
      setVerifiedUpload(uploaded);
      await completeVerifiedUpload(uploaded);
    } catch (cause) { setStage("error"); setError(uploadErrorMessage(cause)); }
  }
  const submitting = stage === "hashing" || stage === "uploading";
  return <div className="speaking"><button className="close" disabled={submitting} onClick={() => go("prepare")} aria-label="Exit recording">×</button><div className="speaking-prompt"><Eyebrow>{assignmentTitle(assignment)}</Eyebrow><p>{assignment.challenge.prompt}</p></div>{stage === "queued" ? <div className="recorder"><p>Your recording was verified and accepted for analysis.</p><small>{queueDurable ? "Analysis is pending. You can leave this page and return later." : "Analysis is pending. The current queue is in memory, so processing is not yet durably delivered."}</small><Button onClick={() => go("home")}>Return home</Button></div> : <><AudioRecorder submitting={submitting} onRecordingReady={recording => void submit(recording)} />{stage === "hashing" && <p className="recorder-status">Securing your recording…</p>}{stage === "uploading" && <p className="recorder-status">Uploading your private recording…</p>}{stage === "error" && <div className="recorder-status" role="alert"><p>{error}</p>{verifiedUpload ? <><p>Your recording upload was accepted. Retry confirmation without uploading it again.</p><Button variant="secondary" onClick={() => void completeVerifiedUpload(verifiedUpload).catch(cause => { setStage("error"); setError(uploadErrorMessage(cause)); })}>Retry confirmation</Button></> : <><p>Keep this recording open and choose “Use this recording” to retry.</p>{pending && <Button variant="secondary" onClick={() => void submit(pending)}>Retry upload</Button>}</>}</div>}</>}</div>;
}

export function Processing({ go }: { go: (v: View) => void }) {
  const [done, setDone] = useState(false); useEffect(() => { const id = window.setTimeout(() => setDone(true), 1800); return () => window.clearTimeout(id); }, []);
  return <div className="processing narrow"><div className="orb" /><Eyebrow>{done ? "Recording ready" : "Recording captured"}</Eyebrow><h1>{done ? "Upload comes next." : "Preparing your recording."}</h1><p>Secure upload and analysis status are the next integration step. Your recording has not been uploaded from this screen.</p>{done ? <Button onClick={() => go("home")}>Return home</Button> : <div className="loading-line" />}</div>;
}
