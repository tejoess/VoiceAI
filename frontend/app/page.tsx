"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, Clock, MessageSquare, Plus, Radio } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent, AnalyticsSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function DashboardPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [providers, setProviders] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.analytics(), api.listAgents(), api.health()])
      .then(([s, a, h]) => {
        setSummary(s);
        setAgents(a);
        setProviders(h.providers);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const stats = [
    { label: "Agents", value: summary?.agents ?? "—", icon: Bot },
    { label: "Test sessions", value: summary?.total_sessions ?? "—", icon: Radio },
    { label: "Avg turns / call", value: summary?.avg_turns ?? "—", icon: MessageSquare },
    {
      label: "Avg duration",
      value: summary ? `${summary.avg_duration_seconds}s` : "—",
      icon: Clock,
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Build and test multilingual voice agents.
          </p>
        </div>
        <Button asChild>
          <Link href="/agents/new">
            <Plus className="h-4 w-4" /> Create agent
          </Link>
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/40">
          <CardContent className="pt-6 text-sm text-destructive">
            Could not reach the backend ({error}). Is the API running on :8000?
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent className="flex items-center gap-4 pt-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/15">
                <s.icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <div className="text-2xl font-semibold">{s.value}</div>
                <div className="text-xs text-muted-foreground">{s.label}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Your agents</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link href="/agents">View all</Link>
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {agents.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No agents yet. Create your first one to get started.
              </p>
            )}
            {agents.slice(0, 5).map((a) => (
              <Link
                key={a.id}
                href={`/agents/${a.id}`}
                className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3 transition-colors hover:bg-secondary"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-secondary">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{a.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {a.primary_language.toUpperCase()} · {a.voice_id}
                    </div>
                  </div>
                </div>
                <Badge variant={a.is_active ? "success" : "muted"}>
                  {a.is_active ? "active" : "paused"}
                </Badge>
              </Link>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Provider status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {["livekit", "deepgram", "openai", "cartesia", "sarvam"].map((p) => (
              <div key={p} className="flex items-center justify-between">
                <span className="text-sm capitalize">{p}</span>
                <Badge variant={providers[p] ? "success" : "muted"}>
                  {providers[p] ? "configured" : "no key"}
                </Badge>
              </div>
            ))}
            <p className="pt-2 text-xs text-muted-foreground">
              Add API keys to the backend <code>.env</code> to enable each provider.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
