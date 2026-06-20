"use client";

import { useEffect, useRef, useState } from "react";
import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { Loader2, Mic, PhoneOff } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type Turn = { role: string; text: string; ts: number };
type Status = "idle" | "connecting" | "live" | "error";

export function VoiceTester({ agent }: { agent: Agent }) {
  const [status, setStatus] = useState<Status>("idle");
  const [language, setLanguage] = useState(agent.primary_language);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState(false);

  // Streaming state: words appear incrementally as they arrive
  const [userPartial, setUserPartial] = useState("");   // interim STT words
  const [agentPartial, setAgentPartial] = useState(""); // LLM tokens as they stream

  const roomRef = useRef<Room | null>(null);
  const audioContainer = useRef<HTMLDivElement | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect();
    };
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, userPartial, agentPartial]);

  async function start() {
    setError(null);
    setNotConfigured(false);
    setTurns([]);
    setUserPartial("");
    setAgentPartial("");
    setStatus("connecting");
    try {
      const conn = await api.connect(agent.id, language);
      if (!conn.livekit_configured || !conn.token) {
        setNotConfigured(true);
        setStatus("idle");
        return;
      }

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room
        .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
          if (track.kind === Track.Kind.Audio && audioContainer.current) {
            const el = track.attach();
            audioContainer.current.appendChild(el);
          }
        })
        .on(RoomEvent.DataReceived, (payload: Uint8Array) => {
          try {
            const msg = JSON.parse(new TextDecoder().decode(payload));

            if (msg.type === "stt_partial") {
              // Interim STT words — update the in-progress user bubble
              setUserPartial(msg.text ?? "");

            } else if (msg.type === "agent_turn_start") {
              // Agent is about to speak — open a fresh streaming agent bubble
              setAgentPartial("");

            } else if (msg.type === "token") {
              // One LLM token streamed — append to the in-progress agent bubble
              setAgentPartial((prev) => prev + (msg.text ?? ""));

            } else if (msg.type === "transcript") {
              // Final, complete turn — commit it and clear the partial
              if (msg.role === "user") setUserPartial("");
              if (msg.role === "assistant") setAgentPartial("");
              setTurns((t) => [
                ...t,
                { role: msg.role, text: msg.text, ts: msg.ts ?? Date.now() / 1000 },
              ]);
            }
          } catch {
            /* ignore non-JSON data frames */
          }
        })
        .on(RoomEvent.Disconnected, () => {
          setStatus("idle");
          setUserPartial("");
          setAgentPartial("");
        });

      await room.connect(conn.url, conn.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setStatus("live");
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }

  async function stop() {
    await roomRef.current?.disconnect();
    roomRef.current = null;
    setStatus("idle");
    setUserPartial("");
    setAgentPartial("");
  }

  const live = status === "live";

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Live test</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col items-center justify-center gap-6 py-6">
            <div className="relative flex h-28 w-28 items-center justify-center">
              {live && (
                <span className="absolute inline-flex h-full w-full rounded-full bg-primary/40 animate-pulse-ring" />
              )}
              <div
                className={cn(
                  "flex h-24 w-24 items-center justify-center rounded-full transition-colors",
                  live ? "bg-primary" : "bg-secondary"
                )}
              >
                <Mic
                  className={cn(
                    "h-9 w-9",
                    live ? "text-primary-foreground" : "text-muted-foreground"
                  )}
                />
              </div>
            </div>

            <Badge
              variant={
                status === "live" ? "success" : status === "error" ? "warning" : "muted"
              }
            >
              {status === "connecting" ? "connecting…" : status}
            </Badge>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Test language</label>
            <Select value={language} onValueChange={setLanguage} disabled={live}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {agent.languages.map((l) => (
                  <SelectItem key={l} value={l}>
                    {l.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!live ? (
            <Button onClick={start} className="w-full" disabled={status === "connecting"}>
              {status === "connecting" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
              Start call
            </Button>
          ) : (
            <Button onClick={stop} variant="destructive" className="w-full">
              <PhoneOff className="h-4 w-4" /> End call
            </Button>
          )}

          {notConfigured && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
              LiveKit isn&apos;t configured on the backend yet. Add{" "}
              <code>LIVEKIT_URL</code>, <code>LIVEKIT_API_KEY</code> and{" "}
              <code>LIVEKIT_API_SECRET</code> to <code>backend/.env</code> and run the
              agent worker to test live audio.
            </p>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}

          <div ref={audioContainer} className="hidden" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transcript</CardTitle>
        </CardHeader>
        <CardContent>
          <div ref={logRef} className="h-[420px] space-y-3 overflow-y-auto pr-1">
            {turns.length === 0 && !userPartial && !agentPartial && (
              <p className="py-12 text-center text-sm text-muted-foreground">
                Start a call and speak — words stream here in real time.
              </p>
            )}

            {/* Committed turns */}
            {turns.map((t, i) => (
              <div
                key={i}
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                  t.role === "user"
                    ? "ml-auto bg-primary/15 text-foreground"
                    : "bg-secondary text-foreground"
                )}
              >
                <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {t.role === "user" ? "You" : agent.name}
                </div>
                {t.text}
              </div>
            ))}

            {/* In-progress user speech (interim STT) */}
            {userPartial && (
              <div className="ml-auto max-w-[85%] rounded-lg bg-primary/8 px-3 py-2 text-sm text-foreground/70">
                <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  You
                </div>
                {userPartial}
                <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-current" />
              </div>
            )}

            {/* In-progress agent response (LLM tokens) */}
            {agentPartial && (
              <div className="max-w-[85%] rounded-lg bg-secondary/60 px-3 py-2 text-sm text-foreground/80">
                <div className="mb-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {agent.name}
                </div>
                {agentPartial}
                <span className="ml-0.5 inline-block h-3 w-0.5 animate-pulse bg-current" />
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
