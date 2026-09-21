const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "/v1").replace(/\/$/, "");
const sessionStorageKey = "oratry.session";

export type ApiUser = { id: string; email: string; preferences: Record<string, unknown>; emailVerifiedAt: string | null; createdAt: string };
export type ChallengeAssignment = {
  assignmentId: string;
  status: string;
  reason: "baseline" | "recommended" | string;
  challenge: { id: string; version: number; prompt: string; preparationGuidance: string; targetSkills: string[]; targetVocabulary: string[]; difficulty: number; targetDurationSeconds: number };
};
export type BaselineResponse = { status: "not_started" | "in_progress" | "completed"; assignments: ChallengeAssignment[]; currentAssignment: ChallengeAssignment | null };
export type MeResponse = ApiUser & { onboardingState: BaselineResponse["status"]; currentAssignment: ChallengeAssignment | null };
export type AttemptSummary = { id: string; status: "uploading" | "queued" | "analyzing" | "analysis_failed" | string; assignmentId: string; createdAt: string };
export type HomeResponse = { onboardingState: BaselineResponse["status"]; currentAssignment: ChallengeAssignment | null; inProgressAttempt: AttemptSummary | null; coachingFocus: null; recentProgress: { completedAttemptCount: number } };
export type Session = { accessToken: string; tokenType: "bearer" };
export type AuthResponse = { user: ApiUser; session: Session };
export type SignUpResponse = { user: ApiUser; activationRequired: true; delivery: "email" | string };
export type DevelopmentOutboxResponse = { messages: { recipient: string; activationUrl: string }[] };
export type StoredSession = AuthResponse;
export type UploadInstruction = { method: "PUT"; url: string; headers: Record<string, string>; objectKey: string; expiresAt: string };
export type UploadAttempt = { id: string; status: "uploading" | "queued" | string; assignmentId: string; createdAt: string; upload: UploadInstruction };
export type UploadCompleteResponse = { id: string; status: "queued" | string; queue: { durable: boolean; delivery: string } };
export type AttemptResponse = { id: string; status: string; assignmentId: string; challenge: ChallengeAssignment["challenge"] };
export type ProgressAttempt = { id: string; status: string; assignmentId: string; createdAt: string; challenge: ChallengeAssignment["challenge"] };
export type ProgressResponse = { attempts: ProgressAttempt[] };
export type PlaybackResponse = { url: string; expiresAt: string; contentType: string };
export type ComparisonEvidence = { attemptId: string; ordinal: number; completedAt: string; overallScore: number | null; metrics: Array<{ name: string; value: unknown; unit?: string }> };
export type ComparisonResponse = { challenge: ChallengeAssignment["challenge"]; original: ComparisonEvidence; retry: ComparisonEvidence };
export type TranscriptWord = { word: string; normalized_word: string; start_time: number | null; end_time: number | null; confidence: number | null };
export type AnalysisResultResponse = {
  attemptId: string;
  analysisVersion: number;
  transcript: { text: string; segments: { text: string; start_time: number | null; end_time: number | null; words: TranscriptWord[] }[]; confidence: number | null };
  objectiveMetrics: { items: Array<{ name: string; value: unknown; unit?: string; source?: string; measurement_kind?: string; reliability?: string; note?: string }> };
  evaluation: { result: { dimensions: Record<string, { score: number; observation: string; interpretation: string; evidence: unknown[] }>; primary_weakness: { dimension: string; observation: string; explanation: string }; recommendation: { action: string; success_criterion: string }; next_exercise: { title: string; instructions: string; duration_seconds: number }; limitations: string[] }; provenance: { provider: string; model: string } };
  scorecard: { overall?: number; dimensions?: Record<string, { score: number | null; rule?: string }> };
  coachingRecommendation: { primaryWeakness: { dimension: string; observation: string; explanation: string }; recommendation: { action: string; success_criterion: string }; nextExercise: { title: string; instructions: string; duration_seconds: number } };
};
export type SkillState = { skill: string; estimatedLevel: number; confidence: number; modelVersion: string };
export type SkillsResponse = { skills: SkillState[] };
export type DictionaryMeaning = { partOfSpeech?: string | null; definitions?: string[]; examples?: string[]; synonyms?: string[]; antonyms?: string[] };
export type DictionaryPayload = { term?: string; phonetic?: string | null; meanings?: DictionaryMeaning[]; examples?: string[]; synonyms?: string[]; antonyms?: string[] };
export type DictionaryEntry = { language: string; term: string; payload: DictionaryPayload; source: string; fetchedAt: string; expiresAt: string | null };
export type VocabularyItem = { id: string; word: string; practiceStatus: "new" | "learning" | "practicing" | "mastered" | string; dictionary: DictionaryEntry | null };
export type VocabularyResponse = { items: VocabularyItem[] };
export type DictionaryLookupResponse = { term: string; dictionary: DictionaryEntry | null };

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) { super(message); this.name = "ApiError"; }
}

function url(path: string) { return `${apiBaseUrl}${path}`; }
async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(url(path), { ...options, headers }); }
  catch { throw new ApiError(0, "network_error", "We couldn't reach Oratry. Check your connection and try again."); }
  if (response.ok) return response.json() as Promise<T>;
  const body = await response.json().catch(() => null) as { code?: string; message?: string } | null;
  throw new ApiError(response.status, body?.code ?? "request_failed", body?.message ?? "Something went wrong. Please try again.");
}

export function readStoredSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try { const raw = window.sessionStorage.getItem(sessionStorageKey); if (!raw) return null; const parsed = JSON.parse(raw) as StoredSession; return parsed.session?.accessToken && parsed.user?.id ? parsed : null; }
  catch { return null; }
}
export function storeSession(value: StoredSession) { window.sessionStorage.setItem(sessionStorageKey, JSON.stringify(value)); }
export function clearStoredSession() { if (typeof window !== "undefined") window.sessionStorage.removeItem(sessionStorageKey); }

export const api = {
  signUp: (email: string, password: string, acceptedTerms: boolean) => request<SignUpResponse>("/auth/sign-up", { method: "POST", body: JSON.stringify({ email, password, acceptedTerms }) }),
  signIn: (email: string, password: string) => request<AuthResponse>("/auth/sign-in", { method: "POST", body: JSON.stringify({ email, password }) }),
  activate: (token: string) => request<AuthResponse>(`/auth/activate?token=${encodeURIComponent(token)}`),
  resendActivation: (email: string) => request<{ accepted: true }>("/auth/resend-activation", { method: "POST", body: JSON.stringify({ email }) }),
  developmentOutbox: () => request<DevelopmentOutboxResponse>("/auth/development-outbox"),
  me: (token: string) => request<MeResponse>("/me", {}, token),
  updatePreferences: (token: string, preferences: Record<string, unknown>) => request<ApiUser>("/me", { method: "PATCH", body: JSON.stringify({ preferences }) }, token),
  startBaseline: (token: string) => request<BaselineResponse>("/baseline/start", { method: "POST" }, token),
  baseline: (token: string) => request<BaselineResponse>("/baseline", {}, token),
  home: (token: string) => request<HomeResponse>("/home", {}, token),
  currentAssignment: (token: string) => request<ChallengeAssignment>("/assignments/current", {}, token),
  createAttempt: (token: string, assignmentId: string, contentType: string, checksumSha256: string, retryOfAttemptId?: string) => request<UploadAttempt>(`/assignments/${assignmentId}/attempts`, { method: "POST", body: JSON.stringify({ contentType, checksumSha256, retryOfAttemptId }) }, token),
  uploadBlob: async (instruction: UploadInstruction, blob: Blob): Promise<void> => {
    let response: Response;
    try { response = await fetch(instruction.url, { method: instruction.method, headers: instruction.headers, body: blob }); }
    catch { throw new ApiError(0, "upload_network_error", "Your recording could not be uploaded. Check your connection and try again."); }
    if (!response.ok) throw new ApiError(response.status, "upload_failed", "Your recording could not be uploaded. Try again before recording a new response.");
  },
  completeUpload: (token: string, attempt: UploadAttempt, durationSeconds: number, contentType: string, byteSize: number) => request<UploadCompleteResponse>(`/attempts/${attempt.id}/upload-complete`, { method: "POST", body: JSON.stringify({ objectKey: attempt.upload.objectKey, durationSeconds, contentType, byteSize }) }, token),
  attempt: (token: string, attemptId: string) => request<AttemptResponse>(`/attempts/${attemptId}`, {}, token),
  result: (token: string, attemptId: string) => request<AnalysisResultResponse>(`/attempts/${attemptId}/result`, {}, token),
  playback: (token: string, attemptId: string) => request<PlaybackResponse>(`/attempts/${attemptId}/recording-playback`, {}, token),
  comparison: (token: string, attemptId: string) => request<ComparisonResponse>(`/attempts/${attemptId}/comparison`, {}, token),
  progress: (token: string) => request<ProgressResponse>("/progress", {}, token),
  skills: (token: string) => request<SkillsResponse>("/progress/skills", {}, token),
  vocabulary: (token: string) => request<VocabularyResponse>("/vocabulary", {}, token),
  lookupDictionary: (token: string, word: string) => request<DictionaryLookupResponse>(`/dictionary/${encodeURIComponent(word)}`, {}, token),
  addVocabulary: (token: string, word: string, lookup = true) => request<VocabularyItem>("/vocabulary", { method: "POST", body: JSON.stringify({ word, lookup, language: "en" }) }, token),
  updateVocabulary: (token: string, itemId: string, practiceStatus: VocabularyItem["practiceStatus"]) => request<VocabularyItem>(`/vocabulary/${encodeURIComponent(itemId)}`, { method: "PATCH", body: JSON.stringify({ practiceStatus }) }, token),
  deleteVocabulary: async (token: string, itemId: string): Promise<void> => { await request<unknown>(`/vocabulary/${encodeURIComponent(itemId)}`, { method: "DELETE" }, token); },
};
