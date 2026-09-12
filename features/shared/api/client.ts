import { challenges, currentChallenge, result } from "../mock-data";
import type { Challenge, Result } from "../types";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "/v1";
async function request<T>(path: string, fallback: T): Promise<T> {
  try { const response = await fetch(`${baseUrl}${path}`, { credentials: "include" }); if (!response.ok) throw new Error(); return response.json() as Promise<T>; } catch { return fallback; }
}
export const api = {
  home: () => request("/home", { activeAssignment: currentChallenge, recentScore: 68 }),
  currentChallenge: () => request<Challenge>("/assignments/current", currentChallenge),
  challenges: () => request<Challenge[]>("/challenges", challenges),
  result: (attemptId: string) => request<Result>(`/attempts/${attemptId}/result`, result),
  progress: () => request("/progress", { scores: [54, 59, 61, 68], attempts: 4 }),
  vocabulary: () => request("/vocabulary", [{ id: "1", term: "salient", meaning: "most noticeable or important", status: "Learning" }, { id: "2", term: "trade-off", meaning: "a balance between two desirable outcomes", status: "Ready" }])
};
