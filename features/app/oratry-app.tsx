"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Activation, Baseline, GoogleCallback, Landing, Onboarding, Signup } from "./auth-flow";
import { Home } from "../home/home";
import { Briefing, Practice, Preparation, Processing, Speaking, type SpeakerNotesMode } from "../practice/practice";
import { Comparison, Feedback, Results, Retry } from "../results/results";
import { Progress, Profile, Vocabulary } from "../account/surfaces";
import { ApiError, api, clearStoredSession, readStoredSession, storeSession, type ApiUser, type AuthResponse, type ChallengeAssignment, type HomeResponse, type MeResponse, type StoredSession } from "../shared/api/client";
import { Shell, type View } from "../ui/shell";

type Bootstrap = { session: StoredSession; me: MeResponse; home: HomeResponse };
const authViews: View[] = ["landing", "signup", "activate", "oauth", "onboarding", "baseline"];

function LoadingScreen() { return <div className="processing narrow"><div className="orb" /><p>Loading your practice…</p></div>; }
function ErrorScreen({ retry }: { retry: () => void }) { return <div className="processing narrow"><h1>We couldn’t load your practice.</h1><p>Check your connection, then try again.</p><button className="button" onClick={retry}>Try again</button></div>; }

export function OratryApp() {
  const [view, setView] = useState<View>(() => typeof window !== "undefined" && window.location.pathname === "/activate" ? "activate" : typeof window !== "undefined" && window.location.pathname === "/oauth/callback" ? "oauth" : "landing"); const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null); const [loading, setLoading] = useState(true); const [loadError, setLoadError] = useState(false); const [assignment, setAssignment] = useState<ChallengeAssignment | null>(null); const [reviewAttemptId, setReviewAttemptId] = useState<string | null>(null); const [retryOfAttemptId, setRetryOfAttemptId] = useState<string | null>(null); const [retryAssignment, setRetryAssignment] = useState<ChallengeAssignment | null>(null); const [practiceNotes, setPracticeNotes] = useState("");
  const load = useCallback(async () => {
    const stored = readStoredSession(); if (!stored) { setBootstrap(null); setLoading(false); return; }
    setLoading(true); setLoadError(false);
    try { const [me, home] = await Promise.all([api.me(stored.session.accessToken), api.home(stored.session.accessToken)]); const next = { session: { ...stored, user: me }, me, home }; storeSession(next.session); setBootstrap(next); setAssignment(home.currentAssignment); setView(me.onboardingState === "not_started" ? "onboarding" : "home"); }
    catch (cause) { if (cause instanceof ApiError && cause.status === 401) { clearStoredSession(); setBootstrap(null); setView("landing"); } else setLoadError(true); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const token = bootstrap?.session.session.accessToken ?? "";
  const authenticated = (result: AuthResponse) => { storeSession(result); void load(); };
  const refresh = useCallback(async () => { await load(); }, [load]);
  const signOut = () => { clearStoredSession(); setBootstrap(null); setAssignment(null); setView("landing"); };
  const saveProfile = (user: ApiUser) => {
    setBootstrap(current => {
      if (!current) return current;
      const session = { ...current.session, user };
      storeSession(session);
      return { ...current, session, me: { ...current.me, ...user } };
    });
  };

  if (loading) return <LoadingScreen />;
  if (loadError) return <ErrorScreen retry={() => void load()} />;
  if (!bootstrap) return view === "signup" ? <Signup go={setView} onAuthenticated={authenticated} /> : view === "activate" ? <Activation go={setView} onAuthenticated={authenticated} /> : view === "oauth" ? <GoogleCallback go={setView} onAuthenticated={authenticated} /> : <Landing go={setView} />;

  const currentAssignment = assignment ?? bootstrap.home.currentAssignment; const practiceAssignment = retryAssignment ?? currentAssignment; const savedNotesMode = bootstrap.me.preferences.speakerNotesMode; const notesMode: SpeakerNotesMode = savedNotesMode === "always" || savedNotesMode === "hidden" || savedNotesMode === "quick_glances" ? savedNotesMode : "quick_glances";
  const content: Record<View, ReactNode> = {
    landing: <Landing go={setView} />, signup: <Signup go={setView} onAuthenticated={authenticated} />, activate: <Activation go={setView} onAuthenticated={authenticated} />, oauth: <GoogleCallback go={setView} onAuthenticated={authenticated} />,
    onboarding: <Onboarding go={setView} token={token} user={bootstrap.me} onPreferencesSaved={saveProfile} />,
    baseline: <Baseline go={setView} token={token} onStarted={refresh} />,
    home: <Home go={setView} home={bootstrap.home} user={bootstrap.me} onResume={() => void refresh()} />,
    practice: <Practice go={setView} assignment={practiceAssignment} />, briefing: <Briefing go={setView} assignment={practiceAssignment} />,
    prepare: <Preparation go={setView} assignment={practiceAssignment} notes={practiceNotes} onNotesChange={setPracticeNotes} />, speak: <Speaking go={setView} assignment={practiceAssignment} token={token} retryOfAttemptId={retryOfAttemptId} notes={practiceNotes} notesMode={notesMode} onQueued={attemptId => { setReviewAttemptId(attemptId); setRetryOfAttemptId(null); setRetryAssignment(null); setPracticeNotes(""); }} />, processing: <Processing go={setView} token={token} attemptId={reviewAttemptId} onCompleted={() => void refresh()} />,
    results: <Results go={setView} token={token} attemptId={reviewAttemptId} onRetry={(attemptId, reviewAttempt) => { setRetryOfAttemptId(attemptId); setRetryAssignment({ assignmentId: reviewAttempt.assignmentId, status: "assigned", reason: "recommended", challenge: reviewAttempt.challenge }); setView("speak"); }} />, feedback: <Feedback go={setView} />, retry: <Retry go={setView} />, comparison: <Comparison go={setView} />, progress: <Progress token={token} onReview={attemptId => { setReviewAttemptId(attemptId); setView("results"); }} />, vocabulary: <Vocabulary token={token} />, profile: <Profile token={token} user={bootstrap.me} onSaved={saveProfile} onSignOut={signOut} />
  };
  if (authViews.includes(view)) return <>{content[view]}</>;
  return <Shell view={view} setView={setView} onSignOut={signOut}>{content[view]}</Shell>;
}
