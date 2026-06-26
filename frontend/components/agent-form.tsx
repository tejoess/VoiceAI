"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Volume2, VolumeX } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent, AgentInput, Catalog } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { KnowledgeBase } from "@/components/knowledge-base";

const DEFAULTS: AgentInput = {
  name: "",
  description: "",
  is_active: true,
  system_prompt:
    "You are a helpful assistant for our business. Help callers with their questions politely and efficiently.",
  greeting: "Hi! Thanks for calling. How can I help you today?",
  fallback_message:
    "Sorry, I didn't quite catch that. Could you please repeat it?",
  voice_id: "cartesia_cindy",
  primary_language: "en",
  languages: ["en"],
  tone: "friendly",
  speaking_style: "conversational",
  capabilities: ["faqs"],
  llm_temperature: 0.7,
  max_tokens: 300,
  stt_provider: "deepgram",
  webhook_url: "",
  settings: {},
};

function Chip({
  active,
  children,
  onClick,
  disabled,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-full border px-3 py-1 text-sm transition-colors disabled:opacity-40",
        active
          ? "border-primary bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}

export function AgentForm({
  initial,
  mode,
  onSaved,
}: {
  initial?: Agent;
  mode: "create" | "edit";
  onSaved?: (updated: Agent) => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [form, setForm] = useState<AgentInput>(
    initial ? toInput(initial) : DEFAULTS
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [ttsProvider, setTtsProvider] = useState<"cartesia" | "sarvam">(
    initial ? (initial.voice_id.startsWith("sarvam_") ? "sarvam" : "cartesia") : "cartesia"
  );
  const audioCtxRef = useRef<AudioContext | null>(null);

  async function previewVoice() {
    if (previewing) return;
    setPreviewing(true);
    try {
      const BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
      const res = await fetch(`${BASE}/tts/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: form.voice_id }),
      });
      if (!res.ok) throw new Error(`TTS preview failed: ${res.status}`);
      const buf = await res.arrayBuffer();
      const sampleRate = parseInt(res.headers.get("X-Sample-Rate") || "16000", 10);
      // Decode raw 16-bit signed PCM → float32 for Web Audio API.
      const int16 = new Int16Array(buf);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
      if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
        audioCtxRef.current = new AudioContext({ sampleRate });
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === "suspended") await ctx.resume();
      const audioBuf = ctx.createBuffer(1, float32.length, sampleRate);
      audioBuf.copyToChannel(float32, 0);
      const src = ctx.createBufferSource();
      src.buffer = audioBuf;
      src.connect(ctx.destination);
      src.onended = () => setPreviewing(false);
      src.start();
    } catch (e) {
      setPreviewing(false);
      setError(`Voice preview failed: ${String(e)}`);
    }
  }

  useEffect(() => {
    api.catalog().then(setCatalog).catch((e) => setError(String(e)));
  }, []);

  const set = <K extends keyof AgentInput>(key: K, value: AgentInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Voices for the active provider only.
  const providerVoices = useMemo(() => {
    if (!catalog) return [];
    return catalog.voices.filter((v) => v.provider === ttsProvider);
  }, [catalog, ttsProvider]);

  function switchProvider(prov: "cartesia" | "sarvam") {
    setTtsProvider(prov);
    if (!catalog) return;
    const voices = catalog.voices.filter((v) => v.provider === prov);
    if (voices.length) set("voice_id", voices[0].id);
    // Only force language to English when switching to Cartesia (English-only TTS).
    // Sarvam keeps whatever language the user already has selected.
    if (prov === "cartesia") {
      set("primary_language", "en");
      set("languages", ["en"]);
    }
  }

  function toggleLanguage(code: string) {
    const has = form.languages.includes(code);
    let next = has
      ? form.languages.filter((c) => c !== code)
      : [...form.languages, code];
    if (next.length === 0) next = [form.primary_language];
    set("languages", next);
  }

  function toggleCapability(id: string) {
    const has = form.capabilities.includes(id);
    set(
      "capabilities",
      has ? form.capabilities.filter((c) => c !== id) : [...form.capabilities, id]
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload: Partial<AgentInput> = {
        ...form,
        languages: Array.from(new Set([form.primary_language, ...form.languages])),
        webhook_url: form.webhook_url || null,
      };
      if (mode === "create") {
        const created = await api.createAgent(payload);
        setCreatedId(created.id);
      } else if (initial) {
        const updated = await api.updateAgent(initial.id, payload);
        setSaved(true);
        onSaved?.(updated);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  if (!catalog) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading configuration…
      </div>
    );
  }

  // After create: show knowledge base upload step before navigating away.
  if (createdId) {
    return (
      <div className="space-y-6">
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-5 py-4">
          <p className="font-medium text-emerald-400">Agent created!</p>
          <p className="text-sm text-muted-foreground mt-1">
            Optionally upload documents below so the agent can answer questions from them. You can also skip and do this later.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Knowledge base</CardTitle>
          </CardHeader>
          <CardContent>
            <KnowledgeBase agentId={createdId} />
          </CardContent>
        </Card>

        <div className="flex gap-3">
          <Button onClick={() => { window.location.href = `/agents/${createdId}`; }}>
            Go to agent
          </Button>
          <Button variant="outline" onClick={() => { window.location.href = `/agents/${createdId}/test`; }}>
            Test voice
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      {/* Identity */}
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Reception Assistant"
                required
              />
            </div>
            <div className="flex items-end justify-between gap-4">
              <div className="space-y-1">
                <Label>Active</Label>
                <p className="text-xs text-muted-foreground">
                  Inactive agents can't be tested.
                </p>
              </div>
              <Switch
                checked={form.is_active}
                onCheckedChange={(v) => set("is_active", v)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              value={form.description ?? ""}
              onChange={(e) => set("description", e.target.value)}
              placeholder="What this agent does"
            />
          </div>
        </CardContent>
      </Card>

      {/* Prompts */}
      <Card>
        <CardHeader>
          <CardTitle>Prompts &amp; messages</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="system_prompt">System prompt</Label>
            <Textarea
              id="system_prompt"
              className="min-h-[120px]"
              value={form.system_prompt}
              onChange={(e) => set("system_prompt", e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              The agent layer. Combined at runtime with global, business, tone,
              language &amp; capability layers.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="greeting">Greeting</Label>
              <Textarea
                id="greeting"
                value={form.greeting}
                onChange={(e) => set("greeting", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="fallback">Fallback message</Label>
              <Textarea
                id="fallback"
                value={form.fallback_message}
                onChange={(e) => set("fallback_message", e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Voice & language */}
      <Card>
        <CardHeader>
          <CardTitle>Voice &amp; language</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Step 1 — provider */}
          <div className="space-y-2">
            <Label>Provider</Label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => switchProvider("cartesia")}
                className={cn(
                  "cursor-pointer rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                  ttsProvider === "cartesia"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                )}
              >
                <div className="font-medium">Cartesia</div>
                <div className="text-xs opacity-70">English voices</div>
              </button>
              <button
                type="button"
                onClick={() => switchProvider("sarvam")}
                className={cn(
                  "cursor-pointer rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                  ttsProvider === "sarvam"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                )}
              >
                <div className="font-medium">Sarvam AI</div>
                <div className="text-xs opacity-70">Indian language voices</div>
              </button>
            </div>
          </div>

          {/* Step 2 — voice + preview */}
          <div className="space-y-2">
            <Label>Voice</Label>
            <div className="flex gap-2">
              <Select value={form.voice_id} onValueChange={(v) => set("voice_id", v)}>
                <SelectTrigger className="flex-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {providerVoices.map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.name} · {v.gender === "female" ? "F" : "M"} · {v.description.split("—")[0].trim()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={previewVoice}
                disabled={previewing}
                title="Preview voice"
              >
                {previewing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Volume2 className="h-4 w-4" />
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Click <Volume2 className="inline h-3 w-3" /> to hear a sample.
            </p>
          </div>

          {/* Step 3 — language */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Primary language</Label>
              <Select
                value={form.primary_language}
                onValueChange={(v) => set("primary_language", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {catalog.languages.map((l) => (
                    <SelectItem key={l.code} value={l.code}>
                      {l.name} {l.native_name !== l.name ? `(${l.native_name})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Supported languages */}
          <div className="space-y-2">
            <Label>Supported languages</Label>
            <div className="flex flex-wrap gap-2">
              {catalog.languages.map((l) => (
                <Chip
                  key={l.code}
                  active={form.languages.includes(l.code)}
                  disabled={l.code === form.primary_language}
                  onClick={() => toggleLanguage(l.code)}
                >
                  {l.name}
                </Chip>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Speech Recognition */}
      <Card>
        <CardHeader>
          <CardTitle>Speech recognition (STT)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            Choose which provider transcribes the caller&apos;s speech. Deepgram gives real-time barge-in detection; Sarvam is optimised for Indian-language accuracy.
          </p>
          <div className="grid grid-cols-2 gap-2">
            {(catalog.stt_providers ?? [
              { id: "deepgram", name: "Deepgram Nova-2", description: "Real-time streaming, best for low latency." },
              { id: "sarvam", name: "Sarvam Saarika v2", description: "Indian-language optimised." },
            ]).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => set("stt_provider", p.id)}
                className={cn(
                  "cursor-pointer rounded-lg border px-4 py-3 text-left text-sm transition-colors",
                  form.stt_provider === p.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                )}
              >
                <div className="font-medium">{p.name}</div>
                <div className="text-xs opacity-70">{p.description}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Tone & style */}
      <Card>
        <CardHeader>
          <CardTitle>Tone &amp; speaking style</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Tone</Label>
            <Select value={form.tone} onValueChange={(v) => set("tone", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {catalog.tones.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Speaking style</Label>
            <Select
              value={form.speaking_style}
              onValueChange={(v) => set("speaking_style", v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {catalog.speaking_styles.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Capabilities */}
      <Card>
        <CardHeader>
          <CardTitle>Capabilities</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            {catalog.capabilities
              .filter((c) => c.id !== "documents")
              .map((c) => {
                const active = form.capabilities.includes(c.id);
                const planned = c.status === "planned";
                return (
                  <div
                    role="button"
                    tabIndex={0}
                    key={c.id}
                    onClick={() => toggleCapability(c.id)}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && toggleCapability(c.id)}
                    className={cn(
                      "flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors select-none",
                      active
                        ? "border-primary bg-primary/10"
                        : "border-border hover:bg-secondary"
                    )}
                  >
                    <span className="text-sm font-medium">{c.name}</span>
                    {planned ? (
                      <span className="text-xs text-amber-400">soon</span>
                    ) : (
                      <div className={cn(
                        "relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200",
                        active ? "bg-primary" : "bg-input"
                      )}>
                        <div className={cn(
                          "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200",
                          active ? "translate-x-[1.125rem]" : "translate-x-0.5"
                        )} />
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        </CardContent>
      </Card>

      {/* Advanced */}
      <Card>
        <CardHeader>
          <CardTitle>LLM &amp; integrations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <div className="flex justify-between">
                <Label>Temperature</Label>
                <span className="text-sm text-muted-foreground">
                  {form.llm_temperature.toFixed(2)}
                </span>
              </div>
              <Slider
                min={0}
                max={1.5}
                step={0.05}
                value={[form.llm_temperature]}
                onValueChange={([v]) => set("llm_temperature", v)}
              />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <Label>Max tokens / reply</Label>
                <span className="text-sm text-muted-foreground">{form.max_tokens}</span>
              </div>
              <Slider
                min={64}
                max={1024}
                step={16}
                value={[form.max_tokens]}
                onValueChange={([v]) => set("max_tokens", v)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="webhook">Webhook URL (optional)</Label>
            <Input
              id="webhook"
              value={form.webhook_url ?? ""}
              onChange={(e) => set("webhook_url", e.target.value)}
              placeholder="https://your-system.com/hooks/voice"
            />
          </div>
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          {mode === "create" ? "Create agent" : "Save changes"}
        </Button>
        {saved && <span className="text-sm text-emerald-400">Saved ✓</span>}
      </div>
    </form>
  );
}

function toInput(a: Agent): AgentInput {
  const { id, business_id, created_at, updated_at, ...rest } = a;
  return rest;
}
