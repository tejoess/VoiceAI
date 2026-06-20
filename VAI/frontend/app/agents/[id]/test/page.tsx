"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { VoiceTester } from "@/components/voice-tester";

export default function TestAgentPage() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getAgent(id).then(setAgent).catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!agent) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`/agents/${id}`}
          className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" /> {agent.name}
        </Link>
        <h1 className="text-2xl font-semibold">Voice testing</h1>
        <p className="text-sm text-muted-foreground">
          Talk to your agent over WebRTC. Allow microphone access when prompted.
        </p>
      </div>
      <VoiceTester agent={agent} />
    </div>
  );
}
