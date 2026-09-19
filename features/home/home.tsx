"use client";
import { Button, Card, Eyebrow } from "../ui/primitives";
import type { View } from "../ui/shell";
import type { HomeResponse, MeResponse } from "../shared/api/client";

export function greetingName(user: MeResponse) {
  const displayName = user.preferences.displayName;
  return typeof displayName === "string" && displayName.trim() ? displayName.trim() : user.email.split("@")[0];
}

export function Home({ go, home, user, onResume }: { go: (v: View) => void; home: HomeResponse; user: MeResponse; onResume: () => void }) {
  const assignment = home.currentAssignment;
  const firstName = greetingName(user);
  if (!assignment) return <div className="page home"><div className="welcome"><Eyebrow>Your learning plan</Eyebrow><h1>Welcome, {firstName}.</h1><p>Your baseline is ready when you are.</p><Button onClick={onResume}>Refresh your assignment</Button></div></div>;
  const challenge = assignment.challenge;
  return <div className="page home"><div className="welcome"><Eyebrow>Your next practice</Eyebrow><h1>Welcome, {firstName}.</h1><p>Small, deliberate practice compounds.</p></div>{home.inProgressAttempt && <Card><Eyebrow>Recording {home.inProgressAttempt.status}</Eyebrow><h2>{home.inProgressAttempt.status === "uploading" ? "An upload is waiting to be finished." : "Your recording is queued for analysis."}</h2><p>{home.inProgressAttempt.status === "uploading" ? "The browser needs the original recording to retry this upload. Return to the same browser tab, or record a new response after the upload is cleared." : "Analysis remains pending; results are not ready yet. This status survives refresh."}</p></Card>}<Card className="feature-card"><div><Eyebrow>{assignment.reason === "baseline" ? "Baseline assessment" : "Recommended practice"} · {Math.round(challenge.targetDurationSeconds / 60)} minutes</Eyebrow><h2>{challenge.prompt}</h2><p>{challenge.preparationGuidance}</p><Button onClick={() => go("briefing")}>Start challenge <span>→</span></Button></div><div className="target"><span>Today’s focus</span><strong>{challenge.targetSkills[0] ?? "Clarity"}</strong><p>{assignment.reason === "baseline" ? "This helps establish your starting point." : "Practice one skill deliberately."}</p></div></Card><div className="home-grid"><Card><Eyebrow>Baseline</Eyebrow><h2>{home.onboardingState === "completed" ? "Complete" : "In progress"}</h2><p>{assignment.reason === "baseline" ? "Complete this challenge to move to the next step." : "Your foundation is established."}</p></Card><Card><Eyebrow>Practice history</Eyebrow><h2>{home.recentProgress.completedAttemptCount}</h2><p>Completed analyzed attempts.</p></Card><Card><Eyebrow>Next step</Eyebrow><h2>Prepare, then speak</h2><p>Take a moment to organize your response before recording.</p></Card></div></div>;
}
