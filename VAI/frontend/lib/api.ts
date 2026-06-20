import type {
  Agent,
  AgentInput,
  AnalyticsSummary,
  Catalog,
  CallSession,
  ConnectResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";

// Mutable data (agents, sessions, analytics) — never serve stale.
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// In-process memory cache for truly static catalog data.
// Survives for the lifetime of the browser tab — catalog never changes at
// runtime so there is no need to re-fetch on every component mount.
let _catalogCache: Catalog | null = null;

async function cachedCatalog(): Promise<Catalog> {
  if (_catalogCache) return _catalogCache;
  const data = await req<Catalog>("/catalog");
  _catalogCache = data;
  return data;
}

export const api = {
  // catalog — static data, cached in memory after first load
  catalog: cachedCatalog,

  // agents
  listAgents: () => req<Agent[]>("/agents"),
  getAgent: (id: string) => req<Agent>(`/agents/${id}`),
  createAgent: (data: Partial<AgentInput>) =>
    req<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (id: string, data: Partial<AgentInput>) =>
    req<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteAgent: (id: string) => req<void>(`/agents/${id}`, { method: "DELETE" }),
  promptPreview: (id: string, language?: string) =>
    req<{ system_prompt: string; active_language: string }>(
      `/agents/${id}/prompt-preview${language ? `?language=${language}` : ""}`
    ),

  // sessions
  connect: (agentId: string, language?: string) =>
    req<ConnectResponse>("/sessions/connect", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, language }),
    }),
  listSessions: (agentId?: string) =>
    req<CallSession[]>(`/sessions${agentId ? `?agent_id=${agentId}` : ""}`),

  // analytics
  analytics: (agentId?: string) =>
    req<AnalyticsSummary>(`/analytics/summary${agentId ? `?agent_id=${agentId}` : ""}`),

  // health
  health: () => req<{ providers: Record<string, boolean>; redis: boolean }>("/health"),
};
