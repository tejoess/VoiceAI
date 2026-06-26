export interface Agent {
  id: string;
  business_id?: string | null;
  name: string;
  description?: string | null;
  is_active: boolean;
  system_prompt: string;
  greeting: string;
  fallback_message: string;
  voice_id: string;
  primary_language: string;
  languages: string[];
  tone: string;
  speaking_style: string;
  capabilities: string[];
  llm_temperature: number;
  max_tokens: number;
  stt_provider: string;
  webhook_url?: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type AgentInput = Omit<
  Agent,
  "id" | "business_id" | "created_at" | "updated_at"
>;

export interface LanguageMeta {
  code: string;
  name: string;
  native_name: string;
  tts_provider: string;
  indian: boolean;
}

export interface VoiceMeta {
  id: string;
  name: string;
  provider: string;
  gender: string;
  languages: string[];
  description: string;
}

export interface NamedPrompt {
  id: string;
  name: string;
  prompt?: string;
  status?: string;
}

export interface SttProviderMeta {
  id: string;
  name: string;
  description: string;
}

export interface Catalog {
  languages: LanguageMeta[];
  voices: VoiceMeta[];
  tones: NamedPrompt[];
  speaking_styles: NamedPrompt[];
  capabilities: NamedPrompt[];
  stt_providers: SttProviderMeta[];
}

export interface CallSession {
  id: string;
  agent_id: string;
  room_name: string;
  channel: string;
  status: string;
  language: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  transcript: { role: string; text: string; ts: number }[];
  metrics: Record<string, unknown>;
  turn_count: number;
  created_at: string;
}

export interface ConnectResponse {
  token: string;
  url: string;
  room_name: string;
  agent_id: string;
  livekit_configured: boolean;
}

export interface AnalyticsSummary {
  agents: number;
  total_sessions: number;
  avg_duration_seconds: number;
  avg_turns: number;
  sessions_by_language: Record<string, number>;
}
