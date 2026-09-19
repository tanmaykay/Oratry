const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "/v1").replace(/\/$/, "");
const sessionStorageKey = "oratry.session";

export type ApiUser = { id: string; email: string; preferences: Record<string, unknown>; createdAt: string };
export type ChallengeAssignment = {
  assignmentId: string;
  status: string;
  reason: "baseline" | "recommended" | string;
  challenge: { id: string; version: number; prompt: string; preparationGuidance: string; targetSkills: string[]; difficulty: number; targetDurationSeconds: number };
};
export type BaselineResponse = { status: "not_started" | "in_progress" | "completed"; assignments: ChallengeAssignment[]; currentAssignment: ChallengeAssignment | null };
export type MeResponse = ApiUser & { onboardingState: BaselineResponse["status"]; currentAssignment: ChallengeAssignment | null };
export type AttemptSummary = { id: string; status: "uploading" | "queued" | "analyzing" | "analysis_failed" | string; assignmentId: string; createdAt: string };
export type HomeResponse = { onboardingState: BaselineResponse["status"]; currentAssignment: ChallengeAssignment | null; inProgressAttempt: AttemptSummary | null; coachingFocus: null; recentProgress: { completedAttemptCount: number } };
export type Session = { accessToken: string; tokenType: "bearer" };
export type AuthResponse = { user: ApiUser; session: Session };
export type StoredSession = AuthResponse;
export type UploadInstruction = { method: "PUT"; url: string; headers: Record<string, string>; objectKey: string; expiresAt: string };
export type UploadAttempt = { id: string; status: "uploading" | "queued" | string; assignmentId: string; createdAt: string; upload: UploadInstruction };
export type UploadCompleteResponse = { id: string; status: "queued" | string; queue: { durable: boolean; delivery: string } };

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
  signUp: (email: string, password: string, acceptedTerms: boolean) => request<AuthResponse>("/auth/sign-up", { method: "POST", body: JSON.stringify({ email, password, acceptedTerms }) }),
  signIn: (email: string, password: string) => request<AuthResponse>("/auth/sign-in", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: (token: string) => request<MeResponse>("/me", {}, token),
  updatePreferences: (token: string, preferences: Record<string, unknown>) => request<ApiUser>("/me", { method: "PATCH", body: JSON.stringify({ preferences }) }, token),
  startBaseline: (token: string) => request<BaselineResponse>("/baseline/start", { method: "POST" }, token),
  baseline: (token: string) => request<BaselineResponse>("/baseline", {}, token),
  home: (token: string) => request<HomeResponse>("/home", {}, token),
  currentAssignment: (token: string) => request<ChallengeAssignment>("/assignments/current", {}, token),
  createAttempt: (token: string, assignmentId: string, contentType: string, checksumSha256: string) => request<UploadAttempt>(`/assignments/${assignmentId}/attempts`, { method: "POST", body: JSON.stringify({ contentType, checksumSha256 }) }, token),
  uploadBlob: async (instruction: UploadInstruction, blob: Blob): Promise<void> => {
    let response: Response;
    try { response = await fetch(instruction.url, { method: instruction.method, headers: instruction.headers, body: blob }); }
    catch { throw new ApiError(0, "upload_network_error", "Your recording could not be uploaded. Check your connection and try again."); }
    if (!response.ok) throw new ApiError(response.status, "upload_failed", "Your recording could not be uploaded. Try again before recording a new response.");
  },
  completeUpload: (token: string, attempt: UploadAttempt, durationSeconds: number, contentType: string, byteSize: number) => request<UploadCompleteResponse>(`/attempts/${attempt.id}/upload-complete`, { method: "POST", body: JSON.stringify({ objectKey: attempt.upload.objectKey, durationSeconds, contentType, byteSize }) }, token),
  attempt: (token: string, attemptId: string) => request<{ id: string; status: string; assignmentId: string }>(`/attempts/${attemptId}`, {}, token),
};
