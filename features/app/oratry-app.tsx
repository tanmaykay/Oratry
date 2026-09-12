"use client";
import { useState } from "react";
import type { ReactNode } from "react";
import { Landing, Signup, Onboarding, Baseline } from "./auth-flow";
import { Home } from "../home/home";
import { Briefing, Practice, Preparation, Processing, Speaking } from "../practice/practice";
import { Comparison, Feedback, Results, Retry } from "../results/results";
import { Progress, Profile, Vocabulary } from "../account/surfaces";
import { Shell, type View } from "../ui/shell";
const authViews: View[] = ["landing", "signup", "onboarding", "baseline"];
export function OratryApp() { const [view, setView] = useState<View>("landing"); const content: Record<View, ReactNode> = { landing: <Landing go={setView} />, signup: <Signup go={setView} />, onboarding: <Onboarding go={setView} />, baseline: <Baseline go={setView} />, home: <Home go={setView} />, practice: <Practice go={setView} />, briefing: <Briefing go={setView} />, prepare: <Preparation go={setView} />, speak: <Speaking go={setView} />, processing: <Processing go={setView} />, results: <Results go={setView} />, feedback: <Feedback go={setView} />, retry: <Retry go={setView} />, comparison: <Comparison go={setView} />, progress: <Progress />, vocabulary: <Vocabulary />, profile: <Profile /> }; if (authViews.includes(view)) return <>{content[view]}</>; return <Shell view={view} setView={setView}>{content[view]}</Shell>; }
